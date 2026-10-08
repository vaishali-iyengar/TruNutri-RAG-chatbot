"""Phase 3 exit criteria, checked on the committed chunks in corpus/chunks/.

These need no raw files, so they also run in CI. The first test re-chunks the
saved trees in corpus/parsed/ and fails if the committed chunks are out of date
(re-run `python -m guidance_rag.ingest chunk`).
"""

import re
from collections import defaultdict

import pytest

from guidance_rag.ingest.chunker import DEFAULT_CHUNKS_DIR, Chunker, read_chunks
from guidance_rag.ingest.parse import read_saved
from guidance_rag.models import BlockType, Chunk
from guidance_rag.registry import load_registry

DOCS = load_registry().included
REGISTRY = {d.doc_id: d for d in DOCS}
CHUNKS: dict[str, list[Chunk]] = {
    d.doc_id: read_chunks(DEFAULT_CHUNKS_DIR / f"{d.doc_id}.jsonl")
    for d in DOCS
    if (DEFAULT_CHUNKS_DIR / f"{d.doc_id}.jsonl").exists()
}
ALL = [c for chunks in CHUNKS.values() for c in chunks]


def test_every_document_has_chunks() -> None:
    assert set(CHUNKS) == {d.doc_id for d in DOCS}


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.doc_id)
def test_committed_chunks_match_the_chunker(doc) -> None:  # type: ignore[no-untyped-def]
    tree = read_saved(doc.doc_id)
    if tree is None:
        pytest.skip("no saved tree in corpus/parsed/")
    expected, _ = Chunker().chunk(tree, doc)
    assert CHUNKS[doc.doc_id] == expected, "re-run: python -m guidance_rag.ingest chunk"


def test_corpus_size_is_in_the_planned_range() -> None:
    assert 700 <= len(ALL) <= 1000
    assert all(c.text.strip() for c in ALL), "empty chunk"
    assert max(c.token_count for c in ALL) <= 1000


def test_chunk_ids_are_unique() -> None:
    ids = [c.chunk_id for c in ALL]
    assert len(ids) == len(set(ids))


def test_every_chunk_has_document_name_publisher_year_and_section() -> None:
    for c in ALL:
        assert c.doc_title and c.publisher and c.year and c.section_heading, c.chunk_id
        assert c.section_heading == c.section_path[-1]
        assert c.embed_text.startswith(f"[{REGISTRY[c.doc_id].short_name}")
        assert "\n[Section: " in c.embed_text
        assert not re.search("[\ue000-\uf8ff]", c.embed_text), c.chunk_id
        assert c.deep_link.startswith(str(c.source_url))


def test_every_recommendation_is_exactly_one_chunk() -> None:
    recs = [c for c in CHUNKS["icmr-nin-dgi-2024"] if c.block_type is BlockType.RECOMMENDATION]
    starts = [c.text.split()[0] for c in recs]
    assert starts.count("RATIONALE") == 17 and starts.count("POINTS") == 17
    assert all(c.section_path[0].startswith("GUIDELINE ") for c in recs)


def table_parts(c: Chunk) -> tuple[list[str], list[str]]:
    """Split a table chunk into its head (title, header) and its row lines."""
    lines = c.text.splitlines()
    if len(lines) > 2 and lines[2].startswith("|---"):
        return lines[:3], lines[3:]
    if len(lines) > 1 and lines[1].startswith("Columns: "):
        return lines[:2], lines[2:]
    return lines[:1], lines[1:]


TABLE_CHUNKS = [c for c in ALL if c.block_type is BlockType.TABLE]


def test_every_table_chunk_starts_with_its_title_and_header() -> None:
    by_table: dict[tuple[str, str], list[tuple[str, ...]]] = defaultdict(list)
    for c in TABLE_CHUNKS:
        head, rows = table_parts(c)
        assert head[0] and not head[0].startswith("|"), f"{c.chunk_id} has no title line"
        assert rows, f"{c.chunk_id} has no rows"
        by_table[(c.doc_id, str(c.table_id))].append(tuple(head))
    for heads in by_table.values():  # pieces of one table repeat the same head
        assert len(set(heads)) == 1


def test_no_table_row_is_cut() -> None:
    for c in TABLE_CHUNKS:
        head, rows = table_parts(c)
        if head[-1].startswith("|---"):
            width = head[1].count("|")
            for row in rows:
                assert row.startswith("| ") and row.endswith(" |"), (c.chunk_id, row)
                assert row.count("|") == width, (c.chunk_id, row)


def test_storage_chart_splits_only_between_food_categories() -> None:
    owner: dict[str, set[str]] = defaultdict(set)
    for c in CHUNKS["foodsafety-cold-storage"]:
        if c.block_type is BlockType.TABLE:
            for row in table_parts(c)[1]:
                owner[row.split(" | ")[0].strip("| ")].add(c.chunk_id)
    assert len(owner) == 13
    assert all(len(chunks) == 1 for chunks in owner.values()), owner


def test_no_chunk_spans_two_sections() -> None:
    # Merged small siblings (3.3) are the only chunks whose text holds several headings.
    for c in ALL:
        if c.subsections:
            assert len(c.subsections) >= 2
            for heading in c.subsections:
                assert re.search(rf"(^|\n\n){re.escape(heading)}\n", c.text), c.chunk_id
