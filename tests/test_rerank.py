"""Reranker input (implementation-plan.md, 4.6): the text it reads and long-text windows."""

from guidance_rag.query.rerank import rerank_text, windows
from tests.test_models import CHUNK


def words(text: str) -> int:
    return len(text.split())


def test_rerank_text_is_section_path_and_body_without_the_document_label() -> None:
    text = rerank_text(CHUNK)

    assert text == "Guideline 9 > Cooking oils and fats\nUse a combination of oils."
    assert "ICMR-NIN" not in text


def test_a_short_text_is_one_window() -> None:
    assert windows("Path\nshort body", budget=50, count=words) == ["Path\nshort body"]


def test_a_long_text_splits_between_lines_and_repeats_the_first_line() -> None:
    rows = [f"| row {i} | a b c |" for i in range(10)]  # 7 words each
    text = "Table > Chart\n" + "\n".join(rows)

    pieces = windows(text, budget=25, count=words)

    assert len(pieces) > 1
    assert all(p.startswith("Table > Chart\n") for p in pieces)
    assert [line for p in pieces for line in p.split("\n")[1:]] == rows  # nothing lost or cut
    assert all(words(p) <= 25 for p in pieces)


def test_a_single_line_over_budget_stays_whole() -> None:
    long_line = " ".join(["word"] * 40)

    assert windows("Path\n" + long_line, budget=10, count=words) == ["Path\n" + long_line]
