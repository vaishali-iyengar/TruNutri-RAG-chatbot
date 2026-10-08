"""Hybrid retrieval (implementation-plan.md, 4.5-4.6).

The steps are tested with hand-made chunks and fake scores. The retriever runs on
the real chunks, indexed with a fake embedder in a throwaway Qdrant folder, with a
fake reranker, so no model is needed.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest

from guidance_rag.config import RetrievalConfig
from guidance_rag.ingest.index import build_index
from guidance_rag.models import ScoredChunk
from guidance_rag.query.rerank import rerank_text
from guidance_rag.query.retriever import Retriever, build_pool, expand_tables, prune, rrf, select
from guidance_rag.store import (
    BM25Index,
    TableRowIndex,
    VectorStore,
    load_chunks,
    table_rows,
    tokenize,
)
from tests.test_embed import FakeEmbedder
from tests.test_models import CHUNK

CONFIG = RetrievalConfig()


def chunk(chunk_id: str, table_id: str | None = None):  # type: ignore[no-untyped-def]
    doc_id = chunk_id.split(":")[0]
    return CHUNK.model_copy(update={"chunk_id": chunk_id, "doc_id": doc_id, "table_id": table_id})


def scored(chunk_id: str, score: float, table_id: str | None = None) -> ScoredChunk:
    return ScoredChunk(chunk=chunk(chunk_id, table_id), score=score)


def unit(*values: float) -> np.ndarray:
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


# --- Fusion and candidate pool (4.5) ---------------------------------------------------


def test_rrf_rewards_items_ranked_well_in_both_lists() -> None:
    # c: 1/63 + 1/61 > b: 1/62 + 1/62 > a: 1/61 > d: 1/63
    assert rrf([["a", "b", "c"], ["c", "b", "d"]], k=60) == ["c", "b", "a", "d"]
    assert rrf([["a", "b"], ["b", "a"]]) == ["a", "b"]  # a tie keeps first-seen order
    assert rrf([["x"], []]) == ["x"]


def test_pool_adds_each_documents_top_hits_to_the_global_list() -> None:
    big = [f"big:{i}" for i in range(40)]
    per_doc = {"big": big, "small": ["small:1", "small:2", "small:3", "small:4"]}

    pool = build_pool(big, per_doc, global_k=30, per_doc_k=3)

    assert pool[:30] == big[:30]
    assert pool[30:] == ["small:1", "small:2", "small:3"]  # big's top 3 are already in
    assert len(pool) == len(set(pool))


def test_a_pooled_table_piece_brings_its_sibling_pieces() -> None:
    tables = {"t1": ["d:t:1", "d:t:2", "d:t:3"], "t2": ["d:u:1", "d:u:2"]}
    chunk_table = {c: t for t, ids in tables.items() for c in ids}

    pool = expand_tables(["d:p:1", "d:t:2", "d:p:2"], tables, chunk_table, limit=8)

    assert pool == ["d:p:1", "d:t:2", "d:t:1", "d:t:3", "d:p:2"]
    assert expand_tables(["d:t:3"], tables, chunk_table, limit=1) == ["d:t:3", "d:t:1"]


def test_prune_drops_near_copies_within_a_document_only() -> None:
    pool = [chunk("a:x:1"), chunk("a:x:2"), chunk("b:x:1"), chunk("a:y:1")]
    same = unit(1, 0, 0)
    vectors = {
        "a:x:1": same,
        "a:x:2": unit(1, 0.01, 0),  # near-copy of a:x:1 -> dropped
        "b:x:1": same,  # same vector, other document -> kept
        "a:y:1": unit(0, 1, 0),
    }

    kept = prune(pool, vectors, dup_cosine=0.97)

    assert [c.chunk_id for c in kept] == ["a:x:1", "b:x:1", "a:y:1"]


def test_prune_keeps_similar_pieces_of_one_table() -> None:
    pool = [chunk("a:t:1", "t1"), chunk("a:t:2", "t1")]
    vectors = {"a:t:1": unit(1, 0), "a:t:2": unit(1, 0.01)}

    assert len(prune(pool, vectors, dup_cosine=0.97)) == 2


# --- Evidence selection (4.6) ----------------------------------------------------------


def test_select_keeps_top_three_per_document_and_orders_documents_by_best_score() -> None:
    ranked = [scored(f"big:{i}", 0.95 - i / 100) for i in range(10)] + [scored("small:1", 0.5)]

    docs = select(ranked, CONFIG, tau=0.3)

    assert [d.doc_id for d in docs] == ["big", "small"]
    assert [len(d.chunks) for d in docs] == [3, 1]


def test_a_small_document_keeps_its_slot_when_a_big_one_scores_higher() -> None:
    ranked = [scored(f"big{d}:{i}", 0.9) for d in range(4) for i in range(5)]
    ranked.append(scored("small:1", 0.4))  # weakest overall, but above tau

    docs = select(ranked, CONFIG.model_copy(update={"max_docs": 5}), tau=0.3)

    assert "small" in [d.doc_id for d in docs]
    assert sum(len(d.chunks) for d in docs) == CONFIG.max_chunks
    assert all(d.chunks for d in docs)


def test_select_trims_to_max_chunks_without_dropping_a_documents_best() -> None:
    ranked = [scored(f"d{d}:{i}", 0.9 - d / 10 - i / 100) for d in range(4) for i in range(3)]
    config = CONFIG.model_copy(update={"max_docs": 4, "per_doc_max": 3, "max_chunks": 8})

    docs = select(ranked, config, tau=0.3)

    assert len(docs) == 4
    assert sum(len(d.chunks) for d in docs) == 8
    assert all(d.chunks[0].chunk.chunk_id.endswith(":0") for d in docs)
    assert [len(d.chunks) for d in docs] == [3, 3, 1, 1]  # the weakest extras go first


def test_once_one_document_qualifies_others_join_at_the_lower_threshold() -> None:
    ranked = [scored("a:1", 0.8), scored("b:1", 0.15), scored("c:1", 0.05)]

    docs = select(ranked, CONFIG, tau=0.2, tau_extra=0.1)

    assert [d.doc_id for d in docs] == ["a", "b"]


def test_without_an_anchor_the_lower_threshold_admits_nothing() -> None:
    ranked = [scored("a:1", 0.15), scored("b:1", 0.12)]

    assert select(ranked, CONFIG, tau=0.2, tau_extra=0.1) == []


def test_select_keeps_the_ranking_order_within_a_document() -> None:
    ranked = [scored("a:1", 0.5), scored("a:2", 0.9), scored("a:3", 0.7)]

    (doc,) = select(ranked, CONFIG, tau=0.3)

    assert [sc.chunk.chunk_id for sc in doc.chunks] == ["a:1", "a:2", "a:3"]
    assert doc.best_score == 0.9


def test_select_applies_the_threshold() -> None:
    ranked = [scored("a:1", 0.8), scored("a:2", 0.29), scored("b:1", 0.1)]

    docs = select(ranked, CONFIG, tau=0.3)

    assert [(d.doc_id, len(d.chunks)) for d in docs] == [("a", 1)]
    assert select(ranked, CONFIG, tau=0.9) == []


def test_one_qualifying_document_gets_up_to_six_chunks() -> None:
    ranked = [scored(f"a:{i}", 0.9 - i / 100) for i in range(10)] + [scored("b:1", 0.1)]

    docs = select(ranked, CONFIG, tau=0.3)

    assert [(d.doc_id, len(d.chunks)) for d in docs] == [("a", CONFIG.single_doc_max)]


def test_select_caps_chunks_per_table() -> None:
    ranked = [scored(f"a:t:{i}", 0.9 - i / 100, table_id="t1") for i in range(4)]
    ranked.append(scored("a:p:1", 0.5))

    (doc,) = select(ranked, CONFIG.model_copy(update={"table_cap": 2}), tau=0.3)

    assert [sc.chunk.chunk_id for sc in doc.chunks] == ["a:t:0", "a:t:1", "a:p:1"]


def test_the_table_cap_counts_each_documents_tables_separately() -> None:
    ranked = [scored(f"a:t:{i}", 0.9, table_id="p1-t1") for i in range(3)]
    ranked += [scored(f"b:t:{i}", 0.8, table_id="p1-t1") for i in range(3)]

    docs = select(ranked, CONFIG.model_copy(update={"table_cap": 2}), tau=0.3)

    assert [(d.doc_id, len(d.chunks)) for d in docs] == [("a", 2), ("b", 2)]


# --- Retriever on the real chunks -------------------------------------------------------

ALL_CHUNKS = load_chunks()
DOC_IDS = sorted({c.doc_id for c in ALL_CHUNKS})


class FakeReranker:
    """Scores a text by the share of query tokens it contains."""

    name = "fake-reranker"

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        terms = set(tokenize(query))
        return [len(terms & set(tokenize(t))) / max(len(terms), 1) for t in texts]


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[VectorStore]:
    root: Path = tmp_path_factory.mktemp("retriever")
    s = VectorStore(path=root / "index")
    build_index(s, FakeEmbedder(), manifest_path=root / "manifest.json")
    yield s
    s.close()


def retriever(store: VectorStore, **config: object) -> Retriever:
    return Retriever(
        store,
        BM25Index(ALL_CHUNKS),
        FakeEmbedder(),
        FakeReranker(),
        RetrievalConfig(**config),
    )


@pytest.mark.parametrize("doc_id", ["foodsafety-cold-storage", "icmr-nin-dgi-2024"])
def test_a_filtered_query_returns_only_the_filtered_document(
    store: VectorStore, doc_id: str
) -> None:
    ev = retriever(store).retrieve("how long does raw chicken keep in the fridge", [doc_id])

    assert ev.docs_searched == [doc_id]
    assert {c.split(":")[0] for c in ev.pool} == {doc_id}
    assert {c.split(":")[0] for c, _ in ev.ranked} == {doc_id}
    assert [d.doc_id for d in ev.documents] in ([doc_id], [])


def test_every_document_reaches_the_pool_of_an_unfiltered_query(store: VectorStore) -> None:
    ev = retriever(store).retrieve("salt intake per day")

    assert ev.docs_searched == DOC_IDS
    assert {c.split(":")[0] for c in ev.pool} == set(DOC_IDS)


def test_without_per_document_slots_the_pool_is_the_global_list(store: VectorStore) -> None:
    ev = retriever(store, per_doc_k=0, table_expand=0, row_k=0).retrieve("salt intake per day")

    assert len(ev.pool) <= CONFIG.global_k


def test_evidence_and_ranking_are_consistent(store: VectorStore) -> None:
    ev = retriever(store).retrieve(
        "How long can raw eggs in the shell be kept in the refrigerator?"
    )

    score = dict(ev.ranked)
    by_score = sorted(score, key=lambda c: -score[c])
    assert [c for c, _ in ev.ranked] == rrf([ev.pool, by_score])  # pool order fused with rerank
    assert sorted(score) == sorted(ev.pool)
    assert set(ev.chunk_ids) <= set(ev.pool)
    assert ev.best_score == max(score.values())
    assert set(ev.timings_ms) == {"embed", "search", "rerank"}


def test_sub_queries_widen_the_pool_and_keep_each_chunks_best_score(store: VectorStore) -> None:
    question = "How long can raw chicken stay in the fridge, and how should it be handled?"
    halves = ["How long can raw chicken stay in the fridge?", "How should raw chicken be handled?"]
    r = retriever(store)

    whole = r.retrieve(question)
    split = r.retrieve(question, sub_queries=halves)

    assert set(whole.pool) <= set(split.pool)
    reranker = FakeReranker()
    for chunk_id, s in split.ranked:
        text = rerank_text(r._chunks[chunk_id])
        scores = [reranker.score(q, [text])[0] for q in [question, *halves]]
        # A chunk's score comes from a query that found it, so it is one of these.
        assert s in scores


def test_each_query_reranks_only_the_chunks_it_found(store: VectorStore) -> None:
    calls: list[tuple[str, int]] = []

    class Counting(FakeReranker):
        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            calls.append((query, len(texts)))
            return super().score(query, texts)

    config = RetrievalConfig(row_k=0)  # table rows add calls of their own (tested below)
    r = Retriever(store, BM25Index(ALL_CHUNKS), FakeEmbedder(), Counting(), config)
    halves = ["How long can raw chicken stay in the fridge?", "How should raw chicken be handled?"]

    ev = r.retrieve("raw chicken fridge and handling", sub_queries=halves)

    assert [q for q, _ in calls] == ["raw chicken fridge and handling", *halves]
    assert all(n < len(ev.pool) for _, n in calls)  # no query scores the whole pool
    assert sum(n for _, n in calls) >= len(ev.pool)  # but every pooled chunk is scored


def test_bm25_only_search_finds_the_exact_term(store: VectorStore) -> None:
    ev = retriever(store, dense=False, rerank=False).retrieve("vanaspati")

    assert "vanaspati" in ev.documents[0].chunks[0].chunk.text.lower()


def test_unknown_filter_and_missing_reranker_raise(store: VectorStore) -> None:
    with pytest.raises(ValueError, match="not in the index"):
        retriever(store).retrieve("salt", ["nhs-eatwell"])
    with pytest.raises(ValueError, match="no reranker"):
        Retriever(store, BM25Index(ALL_CHUNKS), FakeEmbedder(), None, RetrievalConfig())


# --- Table rows (2026-10-08, nutrient questions) ----------------------------------------

NUTRIENT_TABLE = "icmr-nin-dgi-2024:what-are-nutrient-requirements-recommended-dieta:2"


def test_table_rows_carry_caption_and_column_names() -> None:
    chunks = {c.chunk_id: c for c in ALL_CHUNKS}
    rows = dict(table_rows(chunks[NUTRIENT_TABLE]))

    assert rows["Milk"].startswith("Table 1.3. Average values of macronutrients")
    assert rows["Milk"].endswith("Milk: Protein (g) 3.1; Fat (g) 4.2; Carbo hydrates (g) 5; "
                                 "Energy (Kcal) 72; Total dietary fibre (g) 0")  # fmt: skip
    wide = chunks["icmr-nin-dgi-2024:what-are-food-groups:4"]  # "column: value; …" layout
    assert any(label == "Milk/ curd (ml)" for label, _ in table_rows(wide))


def test_a_row_matches_only_when_its_label_shares_a_query_word() -> None:
    rows = TableRowIndex(ALL_CHUNKS)

    milk = rows.search("How much protein does milk have?")
    assert milk and milk[0].chunk.chunk_id == NUTRIENT_TABLE
    assert "Milk: Protein (g) 3.1" in milk[0].row
    # Column names alone ("protein", "energy") don't make a match.
    assert all(h.chunk.chunk_id != NUTRIENT_TABLE for h in rows.search("protein energy fibre"))
    assert rows.search("milk", doc_ids=["who-healthy-diet"]) == []


def test_a_table_found_by_its_row_is_pooled_and_scored_as_the_row(store: VectorStore) -> None:
    question = "How much protein does milk have?"
    with_rows = retriever(store).retrieve(question)
    without = retriever(store, row_k=0).retrieve(question)

    assert NUTRIENT_TABLE in with_rows.pool and NUTRIENT_TABLE not in without.pool
    row = next(h.row for h in TableRowIndex(ALL_CHUNKS).search(question))
    score = dict(with_rows.ranked)[NUTRIENT_TABLE]
    assert score >= FakeReranker().score(question, [row])[0]  # the better of chunk and row
