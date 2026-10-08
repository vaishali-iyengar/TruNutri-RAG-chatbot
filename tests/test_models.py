from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

from guidance_rag.models import (
    Answer,
    AnswerStatus,
    BlockType,
    Chunk,
    Citation,
    Claim,
    DocAnswer,
    DocumentFormat,
    DocumentStatus,
    Domain,
    HeadingRule,
    ParserConfig,
    Refusal,
    RefusalCategory,
    SourceDocument,
)

SOURCE_DOCUMENT = SourceDocument(
    doc_id="icmr-nin-dgi-2024",
    title="Dietary Guidelines for Indians",
    short_name="DGI 2024",
    publisher="ICMR – National Institute of Nutrition",
    year=2024,
    source_url="https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf",
    format=DocumentFormat.PDF,
    domain=Domain.NUTRITION,
    status=DocumentStatus.INCLUDED,
    retrieval_date=date(2026, 10, 4),
    sha256="a" * 64,
)

CHUNK = Chunk(
    chunk_id="icmr-nin-dgi-2024:guideline-9:3",
    doc_id="icmr-nin-dgi-2024",
    doc_title="Dietary Guidelines for Indians",
    publisher="ICMR – National Institute of Nutrition",
    year=2024,
    source_url="https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf",
    retrieval_date=date(2026, 10, 4),
    section_path=["Guideline 9", "Cooking oils and fats"],
    section_heading="Cooking oils and fats",
    page_start=87,
    page_end=88,
    deep_link="https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf#page=87",
    block_type=BlockType.RECOMMENDATION,
    domain=Domain.NUTRITION,
    text="Use a combination of oils.",
    embed_text="[ICMR-NIN · Dietary Guidelines for Indians · 2024]\nUse a combination of oils.",
    token_count=12,
)

CLAIM = Claim(text="Recommends a combination of oils.", chunk_ids=[CHUNK.chunk_id])

DOC_ANSWER = DocAnswer(doc_id="icmr-nin-dgi-2024", claims=[CLAIM])

CITATION = Citation(
    n=1,
    chunk_id=CHUNK.chunk_id,
    doc_id=CHUNK.doc_id,
    doc_title=CHUNK.doc_title,
    publisher=CHUNK.publisher,
    year=CHUNK.year,
    section="Guideline 9 > Cooking oils and fats",
    page=87,
    url=CHUNK.deep_link,
    retrieval_date=CHUNK.retrieval_date,
)

REFUSAL = Refusal(category=RefusalCategory.BODY_WEIGHT, message="I can't help with that.")

ANSWERED = Answer(
    status=AnswerStatus.ANSWERED,
    sections=[DOC_ANSWER],
    citations=[CITATION],
    docs_searched=["icmr-nin-dgi-2024", "who-healthy-diet"],
    trace_id="trace-1",
)

REFUSED = Answer(status=AnswerStatus.OUT_OF_SCOPE, refusal=REFUSAL, trace_id="trace-2")


@pytest.mark.parametrize(
    "instance",
    [SOURCE_DOCUMENT, CHUNK, CLAIM, DOC_ANSWER, CITATION, REFUSAL, ANSWERED, REFUSED],
    ids=lambda m: type(m).__name__,
)
def test_json_round_trip(instance: BaseModel) -> None:
    restored = type(instance).model_validate_json(instance.model_dump_json())

    assert restored == instance


def test_source_document_without_fetch_fields_is_valid() -> None:
    doc = SOURCE_DOCUMENT.model_copy(update={"retrieval_date": None, "sha256": None})

    assert SourceDocument.model_validate(doc.model_dump()).sha256 is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("doc_id", "Not A Slug"),
        ("sha256", "not-a-hash"),
        ("year", 1066),
        ("source_url", "not a url"),
        ("status", "maybe"),
    ],
)
def test_source_document_rejects_bad_values(field: str, value: object) -> None:
    data = SOURCE_DOCUMENT.model_dump(mode="json") | {field: value}

    with pytest.raises(ValidationError):
        SourceDocument.model_validate(data)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate({"text": "x", "chunk_ids": [], "url": "https://made-up.example"})


def test_chunk_requires_a_section_path() -> None:
    with pytest.raises(ValidationError):
        Chunk.model_validate(CHUNK.model_dump() | {"section_path": []})


# --- Parser config ------------------------------------------------------------


def test_parser_config_expands_page_ranges() -> None:
    config = ParserConfig(skip_pages=[1, "3-5", "9"], headings_only_pages=["10-11"])
    assert config.skip_page_set == {1, 3, 4, 5, 9}
    assert config.headings_only_page_set == {10, 11}


@pytest.mark.parametrize(
    "data",
    [
        {"skip_pages": ["one-two"]},
        {"recommendation_regex": "(unclosed"},
        {"headings": [{"level": 1, "min_size": 12, "pattern": "[bad"}]},
        {"headings": [{"level": 7, "min_size": 12}]},
        {"table_strategy": "camelot"},
        {"unknown_setting": True},
    ],
)
def test_invalid_parser_config_is_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ParserConfig.model_validate(data)


def test_heading_rule_size_range_defaults_to_one_size() -> None:
    assert HeadingRule(level=1, min_size=12).size_range == (11.75, 12.25)
    assert HeadingRule(level=1, min_size=20, max_size=28).size_range == (19.75, 28.25)
