"""The pipeline end to end, with a fake retriever and a fake LLM (implementation-plan.md, 6.7).

Also the "nothing else runs" test moved here from 5.6: a refused question never reaches
the retriever or the LLM.
"""

from collections.abc import Sequence

import pytest

from guidance_rag.generator import Generator
from guidance_rag.models import AnswerStatus, RefusalCategory
from guidance_rag.pipeline import Pipeline, RagAnswerer
from guidance_rag.query.analyzer import QueryAnalyzer
from guidance_rag.query.scope_guard import ScopeGuard
from guidance_rag.registry import load_registry
from tests.fakes import (
    DGI_OILS,
    FRIDGE_POULTRY,
    WHO_FATS,
    WHO_SALT,
    FakeLLM,
    FakeRetriever,
    evidence,
    reply,
)

REGISTRY = load_registry()
OIL_REPLY = reply(
    (
        "icmr-nin-dgi-2024",
        [("Repeated heating of vegetable oils results in oxidation of PUFA.", [DGI_OILS])],
    ),
    (
        "who-healthy-diet",
        [
            (
                "Oils rich in polyunsaturated fat include soybean, canola and sunflower oils.",
                [WHO_FATS],
            )
        ],
    ),
)


def pipeline(
    *replies: object, chunks: Sequence[str] = (DGI_OILS, WHO_FATS), guard: ScopeGuard | None = None
) -> tuple[Pipeline, FakeRetriever, FakeLLM]:
    retriever = FakeRetriever(evidence(*chunks))
    llm = FakeLLM(*replies)  # type: ignore[arg-type]
    answerer = RagAnswerer(QueryAnalyzer(REGISTRY), retriever, Generator(llm), REGISTRY)  # type: ignore[arg-type]
    return Pipeline(answerer, guard=guard), retriever, llm


def test_an_answer_is_rendered_end_to_end() -> None:
    p, retriever, llm = pipeline(OIL_REPLY)

    answer = p.run("Which cooking oils should I use, and is it OK to reuse oil after deep frying?")

    assert answer.status is AnswerStatus.ANSWERED
    assert [s.doc_id for s in answer.sections] == ["icmr-nin-dgi-2024", "who-healthy-diet"]
    assert [c.n for c in answer.citations] == [1, 2]
    assert answer.markdown and "[1]" in answer.markdown and "[2]" in answer.markdown
    assert len(answer.trace_id) == 32
    _, _, halves = retriever.calls[0]
    assert len(halves) == 2  # the two-part question was split for retrieval
    assert "Which cooking oils" in llm.requests[0].user  # the LLM sees the question as asked


def test_the_llm_sees_the_question_with_its_document_name_but_retrieval_does_not() -> None:
    p, retriever, llm = pipeline(
        reply(
            (
                "who-healthy-diet",
                [
                    (
                        "In adults, salt intake should be limited to less than 5 grams per day.",
                        [WHO_SALT],
                    )
                ],
            )
        ),
        chunks=[WHO_SALT],
    )

    answer = p.run("What does WHO recommend about daily salt intake?")

    assert answer.status is AnswerStatus.ANSWERED
    assert retriever.calls[0][1] == ["who-healthy-diet"]  # alias filter
    assert "WHO" not in retriever.calls[0][0]  # name replaced in the search query
    assert "What does WHO recommend" in llm.requests[0].user


def test_a_blended_claim_is_dropped_and_the_rest_rendered() -> None:
    blended = reply(
        (
            "icmr-nin-dgi-2024",
            [("Salt intake should be limited to less than 5 grams per day.", [WHO_SALT])],
        ),
        (
            "who-healthy-diet",
            [
                (
                    "In adults, salt intake should be limited to less than 5 grams per day.",
                    [WHO_SALT],
                )
            ],
        ),
    )
    p, _, _ = pipeline(blended, chunks=[WHO_SALT, DGI_OILS])

    answer = p.run("How much salt per day?")

    assert [s.doc_id for s in answer.sections] == ["who-healthy-diet"]
    assert all(c.doc_id == "who-healthy-diet" for c in answer.citations)


def test_no_evidence_is_not_in_corpus_and_names_the_documents_searched() -> None:
    p, _, llm = pipeline(chunks=[])

    answer = p.run("Is kombucha safe to drink every day?")

    assert answer.status is AnswerStatus.NOT_IN_CORPUS
    assert answer.refusal is not None and answer.refusal.category is RefusalCategory.NOT_IN_CORPUS
    assert "Healthy diet (fact sheet) (World Health Organization, 2026)" in answer.refusal.message
    assert answer.markdown == answer.refusal.message
    assert llm.requests == []


def test_a_reply_that_fails_twice_is_not_in_corpus() -> None:
    p, _, llm = pipeline("bad", "still bad")

    assert p.run("Which oils?").status is AnswerStatus.NOT_IN_CORPUS
    assert len(llm.requests) == 2


def test_a_none_reply_is_not_in_corpus() -> None:
    p, _, _ = pipeline(reply(status="none"))

    assert p.run("Is kombucha safe?").status is AnswerStatus.NOT_IN_CORPUS


def test_when_every_claim_is_dropped_the_answer_is_not_in_corpus() -> None:
    p, _, _ = pipeline(
        reply(
            ("foodsafety-cold-storage", [("Fresh chicken pieces keep 5 days.", [FRIDGE_POULTRY])])
        ),
        chunks=[FRIDGE_POULTRY],
    )

    assert (
        p.run("How long does raw chicken keep in the fridge?").status is AnswerStatus.NOT_IN_CORPUS
    )


def test_a_partial_answer_keeps_not_covered() -> None:
    partial = reply(
        (
            "icmr-nin-dgi-2024",
            [("Repeated heating of vegetable oils results in oxidation of PUFA.", [DGI_OILS])],
        ),
        status="partial",
        not_covered="the best frying temperature",
    )
    p, _, _ = pipeline(partial)

    answer = p.run("Can I reuse frying oil, and at what temperature should I fry?")

    assert (
        answer.status is AnswerStatus.PARTIAL
        and answer.not_covered == "the best frying temperature"
    )


def test_an_unknown_document_is_refused_before_retrieval() -> None:
    p, retriever, llm = pipeline()

    answer = p.run("What does the NHS Eatwell Guide say about starchy foods?")

    assert answer.status is AnswerStatus.NOT_IN_CORPUS
    assert answer.refusal is not None and answer.refusal.category is RefusalCategory.UNKNOWN_DOC
    assert "NHS" in answer.refusal.message and "I can search:" in answer.refusal.message
    assert retriever.calls == [] and llm.requests == []


def test_grams_of_salt_are_not_treated_as_a_personal_target() -> None:
    """The output guard removes kcal/kg targets addressed to the reader, not other units.
    (Removal itself is tested in test_scope_guard.py.)"""
    salt = "In adults, salt intake should be limited to less than 5 grams per day."
    you = "You should keep salt below 5 grams and sodium below 2 grams per day."
    p, _, _ = pipeline(
        reply(("who-healthy-diet", [(salt, [WHO_SALT]), (you, [WHO_SALT])])), chunks=[WHO_SALT]
    )

    answer = p.run("How much salt per day?")

    assert answer.status is AnswerStatus.ANSWERED
    assert len(answer.sections[0].claims) == 2


@pytest.mark.parametrize(
    "question",
    [
        "What should I eat to cure my type 2 diabetes?",
        "Give me a 1500 kcal meal plan.",
        "How much should a 30-year-old woman weigh?",
        "How much protein is in 100 g of paneer?",
        "I'm pregnant, what should I eat?",
    ],
)
def test_a_refused_question_never_reaches_retrieval_or_the_llm(question: str) -> None:
    """Moved from 5.6 to the real entry point."""
    p, retriever, llm = pipeline(OIL_REPLY)

    answer = p.run(question)

    assert answer.status is AnswerStatus.OUT_OF_SCOPE and answer.refusal is not None
    if answer.refusal.category is RefusalCategory.NUTRIENT_LOOKUP:
        assert "nutrient" in (answer.markdown or "")
    else:
        assert "registered dietitian" in (answer.markdown or "")
    assert retriever.calls == [] and llm.requests == []
