"""Renderer (implementation-plan.md, 6.6)."""

import re

from guidance_rag.models import Answer, AnswerStatus, Chunk, Claim, DocAnswer
from guidance_rag.registry import load_registry
from guidance_rag.render import CLOSING_LINE, api_response, render_answer
from tests.fakes import CHUNKS, DGI_OILS, WHO_FATS, WHO_SALT

SECTIONS = [
    DocAnswer(
        doc_id="who-healthy-diet",
        claims=[
            Claim(
                text="Unsaturated oils such as soybean and canola are preferable.",
                chunk_ids=[WHO_FATS],
            ),
            Claim(
                text="Adults should limit salt to less than 5 grams a day.",
                chunk_ids=[WHO_SALT, WHO_FATS],
            ),
        ],
    ),
    DocAnswer(
        doc_id="icmr-nin-dgi-2024",
        claims=[
            Claim(
                text="Repeated heating of oils generates harmful compounds.", chunk_ids=[DGI_OILS]
            )
        ],
    ),
]
ORDER = ["icmr-nin-dgi-2024", "who-healthy-diet"]  # DGI scored best


def render() -> Answer:
    return render_answer(SECTIONS, CHUNKS, "trace-1", doc_order=ORDER, docs_searched=ORDER)


def test_two_document_answer_snapshot() -> None:
    oils, fats, salt = CHUNKS[DGI_OILS], CHUNKS[WHO_FATS], CHUNKS[WHO_SALT]

    def cite(n: int, c: Chunk) -> str:
        page = f" · p. {c.page_start}" if c.page_start else ""
        section = " > ".join(c.section_path)
        return f"[{n}] {c.doc_title} · {c.publisher} · {c.year} · §{section}{page} · {c.deep_link}"

    expected = "\n".join(
        [
            f"**{oils.doc_title} — {oils.publisher} ({oils.year})**",
            "- Repeated heating of oils generates harmful compounds. [1]",
            "",
            f"**{fats.doc_title} — {fats.publisher} ({fats.year})**",
            "- Unsaturated oils such as soybean and canola are preferable. [2]",
            "- Adults should limit salt to less than 5 grams a day. [3][2]",
            "",
            CLOSING_LINE,
            "",
            "---",
            cite(1, oils),
            cite(2, fats),
            cite(3, salt),
        ]
    )

    assert render().markdown == expected


def test_sections_follow_the_rerank_order_and_citations_are_numbered_in_reading_order() -> None:
    answer = render()

    assert [s.doc_id for s in answer.sections] == ORDER
    assert [(c.n, c.chunk_id) for c in answer.citations] == [
        (1, DGI_OILS),
        (2, WHO_FATS),
        (3, WHO_SALT),
    ]


def test_citations_come_from_chunk_metadata() -> None:
    answer = render()
    by_chunk = {c.chunk_id: c for c in answer.citations}

    for chunk_id, citation in by_chunk.items():
        chunk = CHUNKS[chunk_id]
        assert (citation.doc_title, citation.publisher, citation.year) == (
            chunk.doc_title,
            chunk.publisher,
            chunk.year,
        )
        assert citation.url == chunk.deep_link and citation.page == chunk.page_start


def test_every_url_starts_with_a_registry_source_url() -> None:
    sources = [str(d.source_url).rstrip("/") for d in load_registry().included]
    answer = render()
    urls = re.findall(r"https?://\S+", answer.markdown or "") + [c.url for c in answer.citations]

    assert urls
    assert all(any(u.startswith(s) for s in sources) for u in urls), urls


def test_a_single_document_answer_has_no_closing_line() -> None:
    answer = render_answer(SECTIONS[1:], CHUNKS, "t")

    assert CLOSING_LINE not in (answer.markdown or "")


def test_a_partial_answer_says_what_is_not_covered() -> None:
    answer = render_answer(
        SECTIONS[1:], CHUNKS, "t", status=AnswerStatus.PARTIAL, not_covered="frying temperatures"
    )

    assert answer.status is AnswerStatus.PARTIAL
    assert "Not covered by these documents: frying temperatures" in (answer.markdown or "")


def test_repeated_document_sections_are_merged() -> None:
    extra = DocAnswer(
        doc_id="who-healthy-diet", claims=[Claim(text="Limit salt.", chunk_ids=[WHO_SALT])]
    )
    sections = [*SECTIONS, extra]

    answer = render_answer(sections, CHUNKS, "t")

    assert [s.doc_id for s in answer.sections].count("who-healthy-diet") == 1


def test_api_response_matches_the_contract() -> None:
    data = api_response(render())

    assert data["status"] == "answered" and data["refusal"] is None
    first = data["sections"][0]
    assert (
        first["doc_id"] == "icmr-nin-dgi-2024" and first["publisher"] == CHUNKS[DGI_OILS].publisher
    )
    assert first["claims"][0] == {
        "text": "Repeated heating of oils generates harmful compounds.",
        "citations": [1],
    }
    assert data["sections"][1]["claims"][1]["citations"] == [3, 2]
    assert data["citations"][0]["url"] == CHUNKS[DGI_OILS].deep_link
    assert data["trace_id"] == "trace-1"
