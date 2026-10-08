"""Renderer (implementation-plan.md, 6.6)."""

import re

from guidance_rag.models import Answer, AnswerStatus, Chunk, Claim, DocAnswer
from guidance_rag.registry import load_registry
from guidance_rag.render import api_response, lead_in, render_answer
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
CITE_AS = {d.doc_id: d.cite_as or d.title for d in load_registry().included}


def render() -> Answer:
    return render_answer(
        SECTIONS, CHUNKS, "trace-1", doc_order=ORDER, docs_searched=ORDER, cite_as=CITE_AS
    )


def test_two_document_answer_snapshot() -> None:
    oils, fats, salt = CHUNKS[DGI_OILS], CHUNKS[WHO_FATS], CHUNKS[WHO_SALT]

    def cite(n: int, c: Chunk) -> str:
        page = f" · p. {c.page_start}" if c.page_start else ""
        section = " > ".join(c.section_path)
        return f"[{n}] {c.doc_title} · {c.publisher} · {c.year} · §{section}{page} · {c.deep_link}"

    expected = "\n".join(
        [
            "According to ICMR-NIN's Dietary Guidelines for Indians, repeated heating of oils "
            "generates harmful compounds [1]. According to WHO's healthy diet fact sheet, "
            "unsaturated oils such as soybean and canola are preferable [2]. Adults should "
            "limit salt to less than 5 grams a day [3][2].",
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


def test_the_answer_is_one_paragraph_of_single_source_sentences() -> None:
    """Brief #5: never blend sources. Each sentence is one claim from one document, and
    a lead-in names the document where the answer moves to it (2026-10-08)."""
    answer = render()
    doc_of = {c.n: c.doc_id for c in answer.citations}

    assert [s.doc_id for s in answer.sentences] == [
        "icmr-nin-dgi-2024",
        "who-healthy-diet",
        "who-healthy-diet",
    ]
    for s in answer.sentences:
        assert {doc_of[n] for n in s.citations} == {s.doc_id}
    starts = [s.text.startswith("According to ") for s in answer.sentences]
    assert starts == [True, True, False]  # only where the document changes
    assert (answer.markdown or "").count("\n\n") == 1  # paragraph, then sources


def test_lead_ins_keep_names_and_acronyms_capitalised() -> None:
    assert lead_in("X", "Milk contains 3.1 g.") == "According to X, milk contains 3.1 g."
    assert lead_in("X", "WHO recommends less salt.") == "According to X, WHO recommends less salt."
    assert lead_in("X", "Indian diets lack fibre.") == "According to X, Indian diets lack fibre."
    assert lead_in("X", "INS 330 is permitted.") == "According to X, INS 330 is permitted."


def test_without_cite_as_the_lead_in_uses_the_title() -> None:
    answer = render_answer(SECTIONS[1:], CHUNKS, "t")

    assert answer.sentences[0].text.startswith(f"According to {CHUNKS[DGI_OILS].doc_title}, ")


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


def test_the_api_answer_lists_sentences_in_reading_order() -> None:
    body = api_response(render())

    assert [a["citations"] for a in body["answer"]] == [[1], [2], [3, 2]]
    assert body["answer"][0]["text"].startswith("According to ICMR-NIN's")
    assert [s["doc_id"] for s in body["sections"]] == ORDER  # still there, per document
