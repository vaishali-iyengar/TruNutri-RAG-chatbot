from typing import Any

import pytest
from pydantic import ValidationError

from eval.golden import (
    ANSWERABLE_CATEGORIES,
    GoldenCategory,
    GoldenEntry,
    GoldenSet,
    load_golden,
)
from guidance_rag.ingest.chunker import DEFAULT_CHUNKS_DIR, read_chunks
from guidance_rag.models import BlockType, RefusalCategory


def test_golden_file_loads_and_validates() -> None:
    golden = load_golden()

    assert golden.version >= 1
    assert len(golden.questions) >= 40


@pytest.mark.parametrize("category", list(GoldenCategory))
def test_every_category_has_at_least_three_questions(category: GoldenCategory) -> None:
    assert len(load_golden().by_category(category)) >= 3


@pytest.mark.parametrize(
    "refusal",
    [
        RefusalCategory.MEDICAL,
        RefusalCategory.CALORIE_TARGET,
        RefusalCategory.BODY_WEIGHT,
        RefusalCategory.NUTRIENT_LOOKUP,
    ],
)
def test_every_out_of_scope_refusal_type_is_covered(refusal: RefusalCategory) -> None:
    questions = load_golden().by_category(GoldenCategory.OUT_OF_SCOPE)

    assert any(q.expected_refusal is refusal for q in questions)


def test_every_entry_is_checked_against_the_sources() -> None:
    unverified = [q.id for q in load_golden().questions if not q.verified]
    assert not unverified, f"check these against corpus/raw/ and set verified: true: {unverified}"


def test_prompt_injection_is_covered() -> None:
    assert any("injection" in q.tags for q in load_golden().questions)


# --- Schema rules ------------------------------------------------------------

VALID_ANSWERABLE: dict[str, Any] = {
    "id": "sd-99",
    "question": "What does WHO say about salt?",
    "category": "single_doc",
    "expected_status": "answered",
    "expected_doc_ids": ["who-healthy-diet"],
    "expected_answer_notes": "Less than 5 g a day.",
}


def test_valid_entry_passes() -> None:
    GoldenEntry.model_validate(VALID_ANSWERABLE)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"expected_doc_ids": ["nhs-eatwell"]}, "unknown doc_ids"),
        ({"expected_doc_ids": ["fssai-fsms-spices"]}, "unknown doc_ids"),
        ({"expected_doc_ids": []}, "need expected_doc_ids"),
        ({"expected_status": "not_in_corpus"}, "must expect an answer"),
        ({"expected_answer_notes": ""}, "need expected_answer_notes"),
        ({"category": "cross_doc"}, "at least 2 expected_doc_ids"),
        ({"category": "doc_filtered"}, "need a doc_filter"),
        (
            {"category": "doc_filtered", "doc_filter": ["icmr-nin-dgi-2024"]},
            "inside doc_filter",
        ),
        ({"id": "bad id"}, "pattern"),
    ],
)
def test_answerable_entry_rules(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GoldenEntry.model_validate(VALID_ANSWERABLE | override)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"category": "out_of_scope", "expected_status": "out_of_scope"},
            "out-of-scope refusal category",
        ),
        (
            {
                "category": "out_of_scope",
                "expected_status": "out_of_scope",
                "expected_refusal": "not_in_corpus",
            },
            "out-of-scope refusal category",
        ),
        (
            {
                "category": "not_in_corpus",
                "expected_status": "not_in_corpus",
                "expected_refusal": "unknown_doc",
            },
            "must expect refusal",
        ),
        (
            {
                "category": "unknown_doc",
                "expected_status": "answered",
                "expected_refusal": "unknown_doc",
            },
            "must expect not_in_corpus",
        ),
        (
            {
                "category": "out_of_scope",
                "expected_status": "out_of_scope",
                "expected_refusal": "medical",
                "expected_doc_ids": ["who-healthy-diet"],
            },
            "must not list expected_doc_ids",
        ),
    ],
)
def test_refusal_entry_rules(data: dict[str, Any], message: str) -> None:
    base = {"id": "xx-01", "question": "Some question here?"}
    with pytest.raises(ValidationError, match=message):
        GoldenEntry.model_validate(base | data)


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate golden ids"):
        GoldenSet.model_validate({"version": 1, "questions": [VALID_ANSWERABLE] * 2})


# --- Gold chunk labels (Phase 3, 3.9) -------------------------------------------------

CHUNKS = {c.chunk_id: c for path in DEFAULT_CHUNKS_DIR.glob("*.jsonl") for c in read_chunks(path)}
ANSWERABLE = [q for q in load_golden().questions if q.category in ANSWERABLE_CATEGORIES]


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_answerable_questions_have_valid_gold_chunks(question: GoldenEntry) -> None:
    assert question.gold_chunk_ids, "label the chunk(s) that contain the answer"
    missing = [i for i in question.gold_chunk_ids if i not in CHUNKS]
    assert not missing, f"not in corpus/chunks/ (re-chunked?): {missing}"
    docs = {CHUNKS[i].doc_id for i in question.gold_chunk_ids}
    assert docs <= set(question.expected_doc_ids)
    if question.category is GoldenCategory.CROSS_DOC:
        assert docs == set(question.expected_doc_ids), "each expected document needs a gold chunk"


@pytest.mark.parametrize(
    "question", load_golden().by_category(GoldenCategory.RECOMMENDATION), ids=lambda q: q.id
)
def test_recommendation_answers_include_a_whole_recommendation_chunk(
    question: GoldenEntry,
) -> None:
    kinds = {CHUNKS[i].block_type for i in question.gold_chunk_ids}
    assert BlockType.RECOMMENDATION in kinds


def test_refused_questions_have_no_gold_chunks() -> None:
    refused = [q for q in load_golden().questions if q.category not in ANSWERABLE_CATEGORIES]
    assert not [q.id for q in refused if q.gold_chunk_ids]
