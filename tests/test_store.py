"""Vector store, indexer and BM25 (implementation-plan.md, 4.3-4.4).

The vector tests use a fake embedder and a throwaway Qdrant folder; the BM25
tests run on the real chunks in corpus/chunks/.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from guidance_rag.ingest.chunker import DEFAULT_CHUNKS_DIR, read_chunks
from guidance_rag.ingest.index import build_index
from guidance_rag.store import BM25Index, VectorStore, load_chunks, point_id, tokenize
from tests.test_embed import FakeEmbedder

ALL_CHUNKS = load_chunks()
DOC_IDS = sorted({c.doc_id for c in ALL_CHUNKS})


@pytest.fixture
def store(tmp_path: Path):  # type: ignore[no-untyped-def]
    s = VectorStore(path=tmp_path / "index")
    yield s
    s.close()


@pytest.fixture
def chunks_dir(tmp_path: Path) -> Path:
    """A private copy of corpus/chunks/ that tests can change."""
    target = tmp_path / "chunks"
    shutil.copytree(DEFAULT_CHUNKS_DIR, target)
    return target


def index(store: VectorStore, chunks_dir: Path, tmp_path: Path, **kwargs):  # type: ignore[no-untyped-def]
    return build_index(
        store,
        kwargs.pop("embedder", FakeEmbedder()),
        chunks_dir=chunks_dir,
        manifest_path=tmp_path / "manifest.json",
        **kwargs,
    )


# --- Vector store and indexer (4.3) --------------------------------------------------


def test_full_index_holds_one_point_per_chunk(
    store: VectorStore, chunks_dir: Path, tmp_path: Path
) -> None:
    report = index(store, chunks_dir, tmp_path)
    assert store.count() == len(ALL_CHUNKS)
    assert report.indexed == {d: sum(c.doc_id == d for c in ALL_CHUNKS) for d in DOC_IDS}
    for doc_id, n in report.indexed.items():
        assert store.count(doc_id) == n


def test_second_run_skips_unchanged_documents(
    store: VectorStore, chunks_dir: Path, tmp_path: Path
) -> None:
    index(store, chunks_dir, tmp_path)
    fake = FakeEmbedder()
    report = index(store, chunks_dir, tmp_path, embedder=fake)
    assert report.indexed == {} and sorted(report.skipped) == DOC_IDS
    assert fake.calls == []
    assert store.count() == len(ALL_CHUNKS)


def test_reindexing_one_document_leaves_the_others_untouched(
    store: VectorStore, chunks_dir: Path, tmp_path: Path
) -> None:
    index(store, chunks_dir, tmp_path)
    before = {d: store.count(d) for d in DOC_IDS}

    path = chunks_dir / "who-healthy-diet.jsonl"
    path.write_text("".join(path.read_text().splitlines(keepends=True)[:5]))  # 17 -> 5 chunks
    report = index(store, chunks_dir, tmp_path)

    assert report.indexed == {"who-healthy-diet": 5}
    assert store.count("who-healthy-diet") == 5
    assert {d: store.count(d) for d in DOC_IDS if d != "who-healthy-diet"} == {
        d: n for d, n in before.items() if d != "who-healthy-diet"
    }


def test_a_new_model_rebuilds_the_collection(
    store: VectorStore, chunks_dir: Path, tmp_path: Path
) -> None:
    index(store, chunks_dir, tmp_path)
    report = index(store, chunks_dir, tmp_path, embedder=FakeEmbedder("new-model", dim=8))
    assert report.rebuilt and sorted(report.indexed) == DOC_IDS
    assert store.count() == len(ALL_CHUNKS)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert (manifest["model"], manifest["dim"]) == ("new-model", 8)


def test_a_removed_chunk_file_removes_its_points(
    store: VectorStore, chunks_dir: Path, tmp_path: Path
) -> None:
    index(store, chunks_dir, tmp_path)
    (chunks_dir / "foodsafety-cold-storage.jsonl").unlink()
    report = index(store, chunks_dir, tmp_path)
    assert report.removed == ["foodsafety-cold-storage"]
    assert store.count("foodsafety-cold-storage") == 0


def test_index_only_named_documents(store: VectorStore, chunks_dir: Path, tmp_path: Path) -> None:
    report = index(store, chunks_dir, tmp_path, doc_ids=["jecfa-trs-1058"])
    assert list(report.indexed) == ["jecfa-trs-1058"]
    assert store.count() == store.count("jecfa-trs-1058") > 0
    with pytest.raises(ValueError, match="no chunk file"):
        index(store, chunks_dir, tmp_path, doc_ids=["nhs-eatwell"])


def test_vector_search_returns_whole_chunks_and_respects_the_filter(
    store: VectorStore, chunks_dir: Path, tmp_path: Path
) -> None:
    fake = FakeEmbedder()
    index(store, chunks_dir, tmp_path, embedder=fake)
    target = next(c for c in ALL_CHUNKS if c.doc_id == "who-healthy-diet")

    top = store.search(fake.embed_documents([target.embed_text])[0], limit=1)[0]
    assert top.chunk == target  # payload round-trips to the same Chunk
    assert top.score == pytest.approx(1.0, abs=1e-5)

    query = fake.embed_query("anything")
    for doc_ids in (["foodsafety-cold-storage"], ["who-healthy-diet", "jecfa-trs-1058"]):
        hits = store.search(query, doc_ids=doc_ids, limit=40)
        assert hits and {h.chunk.doc_id for h in hits} <= set(doc_ids)
    assert len(store.search(query, doc_ids=["foodsafety-cold-storage"], limit=40)) == 5


def test_replace_document_checks_its_input(store: VectorStore) -> None:
    store.ensure_collection(4)
    chunk = ALL_CHUNKS[0]
    with pytest.raises(ValueError, match="one vector per chunk"):
        store.replace_document(chunk.doc_id, [chunk], np.zeros((2, 4), dtype=np.float32))
    with pytest.raises(ValueError, match="must belong to"):
        store.replace_document("other-doc", [chunk], np.zeros((1, 4), dtype=np.float32))


def test_point_ids_are_stable_uuids() -> None:
    assert point_id("who-healthy-diet:sugars:1") == point_id("who-healthy-diet:sugars:1")
    assert point_id("who-healthy-diet:sugars:1") != point_id("who-healthy-diet:sugars:2")


# --- BM25 (4.4) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("Keep at 4 °C or below", ["keep", "4°c", "4", "below"]),
        ("4ºC", ["4°c", "4"]),
        ("40°F (4°C)", ["40°f", "40", "4°c", "4"]),
        ("3–4 days", ["3", "4", "day"]),
        ("3 to 4 days", ["3", "4", "day"]),
        ("0–5 mg/kg bw", ["0", "5", "mg/kg", "bw"]),
        ("INS No. 473", ["ins", "no", "473"]),  # short words keep their final "s"
        ("Raw eggs in shell", ["raw", "egg", "shell"]),
        ("glass", ["glass"]),
    ],
)
def test_tokenize(text: str, tokens: list[str]) -> None:
    assert tokenize(text) == tokens


@pytest.fixture(scope="module")
def bm25() -> BM25Index:
    return BM25Index(ALL_CHUNKS)


@pytest.mark.parametrize(
    ("query", "must_contain"),
    [
        ("vanaspati", "vanaspati"),
        ("40°F", "40°F"),
        ("INS No. 473", "INS No. 473"),
        ("HACCP plan frozen peas", "Frozen Peas"),
    ],
)
def test_exact_terms_rank_a_chunk_containing_them_first(
    bm25: BM25Index, query: str, must_contain: str
) -> None:
    top = bm25.search(query, limit=1)[0]
    assert must_contain.lower() in (top.chunk.text + " ".join(top.chunk.section_path)).lower()


def test_bm25_filter_returns_only_the_named_documents(bm25: BM25Index) -> None:
    hits = bm25.search("raw eggs in shell", doc_ids=["foodsafety-cold-storage"], limit=40)
    assert hits and {h.chunk.doc_id for h in hits} == {"foodsafety-cold-storage"}
    assert hits[0].chunk.chunk_id == "foodsafety-cold-storage:cold-food-storage-chart:4"


def test_bm25_ignores_chunks_without_any_query_term(bm25: BM25Index) -> None:
    assert bm25.search("zzzunknownterm") == []
    assert bm25.search("the of and") == []  # only stop words


def test_bm25_text_leaves_out_the_document_label() -> None:
    from guidance_rag.store import bm25_text

    chunk = read_chunks(DEFAULT_CHUNKS_DIR / "fssai-fsms-milk.jsonl")[0]
    assert "FSSAI FSMS Milk" not in bm25_text(chunk)
    assert chunk.section_path[0] in bm25_text(chunk)
