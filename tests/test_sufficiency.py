"""Sufficiency gate (implementation-plan.md, 7.1-7.2) and its place in the pipeline (7.4)."""

import json

import pytest

from guidance_rag.generator import Generator
from guidance_rag.llm import LLMError, LLMResponse
from guidance_rag.models import AnswerStatus, RefusalCategory
from guidance_rag.pipeline import Pipeline, RagAnswerer
from guidance_rag.query.analyzer import QueryAnalyzer
from guidance_rag.registry import load_registry
from guidance_rag.sufficiency import (
    EvidenceChecker,
    SufficiencyGate,
    Verdict,
    score_check,
    verdict_schema,
)
from tests.fakes import (
    DGI_OILS,
    WHO_FATS,
    WHO_SALT,
    FakeLLM,
    FakeRetriever,
    evidence,
    reply,
)

REGISTRY = load_registry()
SALT = evidence(WHO_SALT)  # best score 0.9 (see tests.fakes.evidence)


def verdict(v: str, chunks: list[str] | None = None, not_covered: str | None = None) -> str:
    return json.dumps(
        {"verdict": v, "supporting_chunk_ids": chunks or [], "not_covered": not_covered}
    )


# --- Score check (7.1) -------------------------------------------------------------------


@pytest.mark.parametrize(("tau", "passes"), [(0.89, True), (0.9, True), (0.91, False)])
def test_score_check_on_both_sides_of_the_threshold(tau: float, passes: bool) -> None:
    assert score_check(SALT, tau) is passes


def test_no_evidence_fails_the_score_check() -> None:
    assert not score_check(evidence(), 0.0)


def test_the_gate_stops_a_low_score_before_the_llm() -> None:
    llm = FakeLLM()

    result = SufficiencyGate(0.95, EvidenceChecker(llm)).assess("Salt?", SALT)

    assert not result.sufficient and result.reason == "score below tau_answer"
    assert llm.requests == []


# --- Evidence check (7.2) -------------------------------------------------------------


def test_yes_passes() -> None:
    llm = FakeLLM(verdict("yes", [WHO_SALT]))

    result = SufficiencyGate(0.3, EvidenceChecker(llm)).assess("Salt?", SALT)

    assert result.sufficient and result.verdict is not None
    assert result.verdict.verdict is Verdict.YES and result.verdict.supporting == [WHO_SALT]
    assert result.not_covered is None
    assert llm.requests[0].model == "openai/gpt-oss-20b"


def test_partial_passes_and_carries_the_gap() -> None:
    llm = FakeLLM(verdict("partial", [WHO_SALT], "potassium for children"))

    result = SufficiencyGate(0.3, EvidenceChecker(llm)).assess("Salt and potassium?", SALT)

    assert result.sufficient and result.not_covered == "potassium for children"


def test_no_fails() -> None:
    llm = FakeLLM(verdict("no"))

    result = SufficiencyGate(0.3, EvidenceChecker(llm)).assess("Is kombucha safe?", SALT)

    assert not result.sufficient and result.reason == "evidence check: no"


def test_a_failed_check_is_retried_once_then_lets_the_question_through() -> None:
    llm = FakeLLM(LLMError("rate limited"), LLMResponse('{"verdict": "y', "length"))

    result = SufficiencyGate(0.3, EvidenceChecker(llm)).assess("Salt?", SALT)

    assert result.sufficient and result.notes == ["evidence check unavailable"]
    assert len(llm.requests) == 2


def test_the_verdict_schema_meets_strict_rules_and_limits_ids() -> None:
    schema = verdict_schema(SALT)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["supporting_chunk_ids"]["items"]["enum"] == [WHO_SALT]


# --- In the pipeline (7.4) --------------------------------------------------------------

OIL_REPLY = reply(
    (
        "icmr-nin-dgi-2024",
        [("Repeated heating of vegetable oils results in oxidation of PUFA.", [DGI_OILS])],
    ),
    (
        "who-healthy-diet",
        [("Oils rich in polyunsaturated fat include soybean and sunflower oils.", [WHO_FATS])],
    ),
)


def pipeline(
    *check_replies: str, tau: float = 0.3, chunks: tuple[str, ...] = (DGI_OILS, WHO_FATS)
) -> tuple[Pipeline, FakeRetriever, FakeLLM, FakeLLM]:
    retriever = FakeRetriever(evidence(*chunks))
    generator_llm, checker_llm = FakeLLM(OIL_REPLY), FakeLLM(*check_replies)
    gate = SufficiencyGate(tau, EvidenceChecker(checker_llm))
    answerer = RagAnswerer(
        QueryAnalyzer(REGISTRY),
        retriever,  # type: ignore[arg-type]
        Generator(generator_llm),
        REGISTRY,
        gate,
    )
    return Pipeline(answerer), retriever, generator_llm, checker_llm


def test_a_sufficient_answer_is_generated() -> None:
    p, _, generator_llm, _ = pipeline(verdict("yes", [DGI_OILS]))

    answer = p.run("Which cooking oils should I use, and can I reuse frying oil?")

    assert answer.status is AnswerStatus.ANSWERED
    assert len(generator_llm.requests) == 1


def test_a_score_failure_is_not_in_corpus_and_skips_both_llms() -> None:
    p, _, generator_llm, checker_llm = pipeline(tau=0.95)

    answer = p.run("Which cooking oils should I use?")

    assert answer.status is AnswerStatus.NOT_IN_CORPUS
    assert answer.refusal is not None and answer.refusal.category is RefusalCategory.NOT_IN_CORPUS
    assert generator_llm.requests == [] and checker_llm.requests == []


def test_an_evidence_check_failure_is_not_in_corpus_and_skips_the_generator() -> None:
    p, _, generator_llm, _ = pipeline(verdict("no"))

    answer = p.run("Is kombucha safe to drink every day?")

    assert answer.status is AnswerStatus.NOT_IN_CORPUS
    assert generator_llm.requests == []


def test_a_partial_verdict_makes_a_partial_answer() -> None:
    p, _, _, _ = pipeline(verdict("partial", [DGI_OILS], "the best frying temperature"))

    answer = p.run("Can I reuse frying oil, and at what temperature should I fry?")

    assert answer.status is AnswerStatus.PARTIAL
    assert answer.not_covered == "the best frying temperature"
    assert "Not covered by these documents: the best frying temperature" in (answer.markdown or "")


def test_an_unknown_document_is_refused_before_retrieval_and_both_llms() -> None:
    p, retriever, generator_llm, checker_llm = pipeline()

    answer = p.run("What does the FDA say about mercury in tuna?")

    assert answer.refusal is not None and answer.refusal.category is RefusalCategory.UNKNOWN_DOC
    assert retriever.calls == [] and generator_llm.requests == [] and checker_llm.requests == []


def test_a_filtered_miss_lists_only_the_filtered_document() -> None:
    """7.3 exit criterion: the refusal names only what was searched."""
    filtered = evidence(WHO_SALT).model_copy(update={"docs_searched": ["who-healthy-diet"]})
    retriever = FakeRetriever(filtered)
    gate = SufficiencyGate(0.3, EvidenceChecker(FakeLLM(verdict("no"))))
    answerer = RagAnswerer(
        QueryAnalyzer(REGISTRY),
        retriever,  # type: ignore[arg-type]
        Generator(FakeLLM()),
        REGISTRY,
        gate,
    )

    answer = Pipeline(answerer).run("How long do eggs keep in the fridge?", ["who-healthy-diet"])

    assert answer.status is AnswerStatus.NOT_IN_CORPUS
    assert answer.docs_searched == ["who-healthy-diet"]
    assert answer.refusal is not None
    assert "Healthy diet (fact sheet) (World Health Organization, 2026)" in answer.refusal.message
    others = [d for d in REGISTRY.included if d.doc_id != "who-healthy-diet"]
    assert all(d.title not in answer.refusal.message for d in others)
