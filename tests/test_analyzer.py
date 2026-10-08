"""Query analyzer (implementation-plan.md, 4.7), on the real registry."""

import pytest

from eval.golden import GoldenCategory, load_golden
from guidance_rag.query.analyzer import (
    AnalysisStatus,
    QueryAnalyzer,
    UnknownDocumentError,
    question_sentences,
    split_question,
)

ANALYZER = QueryAnalyzer()
DGI = "icmr-nin-dgi-2024"


def test_explicit_filter_is_used_as_given() -> None:
    result = ANALYZER.analyze("What does WHO say about salt?", ["fssai-fsms-milk"])

    assert result.status is AnalysisStatus.OK
    assert result.doc_ids == ["fssai-fsms-milk"]


def test_explicit_filter_with_an_unknown_id_raises() -> None:
    with pytest.raises(UnknownDocumentError, match="nhs-eatwell"):
        ANALYZER.analyze("starchy foods", ["nhs-eatwell"])


@pytest.mark.parametrize(
    ("question", "doc_id"),
    [
        ("What does ICMR say about millets?", DGI),
        ("Summarise the Dietary Guidelines for Indians on oils", DGI),
        ("What does the Dietry Guideline for Indian say about millets?", DGI),  # fuzzy
        ("What did JECFA conclude about adipic acid?", "jecfa-trs-1058"),
        ("Check the USDA fridge chart for eggs", "foodsafety-cold-storage"),
    ],
)
def test_alias_sets_the_filter(question: str, doc_id: str) -> None:
    result = ANALYZER.analyze(question)

    assert result.status is AnalysisStatus.OK
    assert result.doc_ids == [doc_id]


def test_acronyms_match_case_sensitively() -> None:
    result = ANALYZER.analyze("What must people who handle milk do?")

    assert result.doc_ids is None


def test_a_longer_alias_hides_the_shorter_one_inside_it() -> None:
    result = ANALYZER.analyze("What did the Joint FAO/WHO Expert Committee on Food Additives say?")

    assert result.doc_ids == ["jecfa-trs-1058"]


def test_no_alias_searches_everything() -> None:
    result = ANALYZER.analyze("How long do cooked leftovers keep?")

    assert result.status is AnalysisStatus.OK
    assert result.doc_ids is None


@pytest.mark.parametrize(
    "question",
    [
        "What does the NHS Eatwell Guide say about starchy foods?",
        "What does the FDA say about mercury in tuna?",
        "According to USDA MyPlate, how much dairy?",
        "Compare WHO and the NHS on salt",
    ],
)
def test_naming_a_source_outside_the_corpus_gives_unknown_doc(question: str) -> None:
    assert ANALYZER.analyze(question).status is AnalysisStatus.UNKNOWN_DOC


def test_golden_questions() -> None:
    """Unknown-document questions, and only those, get UNKNOWN_DOC; alias filters never
    exclude an expected document."""
    for q in load_golden().questions:
        result = ANALYZER.analyze(q.question, q.doc_filter)
        expect_unknown = q.category is GoldenCategory.UNKNOWN_DOC
        assert (result.status is AnalysisStatus.UNKNOWN_DOC) == expect_unknown, q.id
        if result.doc_ids and q.expected_doc_ids:
            assert set(result.doc_ids) <= set(q.expected_doc_ids), q.id


@pytest.mark.parametrize(
    ("question", "query"),
    [
        (
            "What does the Dietary Guidelines for Indians recommend about physical activity?",
            "What does the guidance recommend about physical activity?",
        ),
        ("What is the Indian dietary guideline on salt?", "What is the guidance on salt?"),
        (
            "What does the Dietry Guideline for Indian say about millets?",
            "What does the guidance say about millets?",
        ),
        ("What does the ICMR guidance say about ghee?", "What does the guidance say about ghee?"),
        ("Summarise WHO's advice on fats", "Summarise the guidance's advice on fats"),
    ],
)
def test_the_search_query_drops_the_document_name(question: str, query: str) -> None:
    assert ANALYZER.analyze(question).query == query


def test_the_search_query_is_the_question_without_an_alias_match() -> None:
    question = "How long do cooked leftovers keep?"

    assert ANALYZER.analyze(question).query == question
    assert (
        ANALYZER.analyze("What does WHO say?", ["who-healthy-diet"]).query == "What does WHO say?"
    )


@pytest.mark.parametrize(
    ("question", "halves"),
    [
        (
            "How long can raw chicken stay in the fridge, and how should it be handled?",
            ["How long can raw chicken stay in the fridge?", "How should raw chicken be handled?"],
        ),
        (  # a dummy "it" is left alone
            "Which cooking oils should I use, and is it OK to reuse oil after deep frying?",
            ["Which cooking oils should I use?", "Is it OK to reuse oil after deep frying?"],
        ),
        ("How much salt and sugar should I eat?", []),  # one question
        ("What does WHO say about salt?", []),
    ],
)
def test_two_part_questions_are_split(question: str, halves: list[str]) -> None:
    assert split_question(question) == halves


def test_the_analyzer_splits_the_search_query() -> None:
    result = ANALYZER.analyze("What does WHO say about salt, and is it OK to use rock salt?")

    assert result.doc_ids == ["who-healthy-diet"]
    assert result.sub_queries == [
        "What does the guidance say about salt?",
        "Is it OK to use rock salt?",
    ]


def test_each_question_sentence_is_also_searched() -> None:
    """9.3 red team: a preamble or a half in another language mustn't drown the question."""
    analysis = QueryAnalyzer().analyze(
        "I'm cooking for my family. Is it OK to reuse the oil left after deep frying?"
    )
    assert analysis.sub_queries == ["Is it OK to reuse the oil left after deep frying?"]

    mixed = QueryAnalyzer().analyze("WHO salt ke baare mein kya kehta hai? How much salt per day?")
    assert "How much salt per day?" in mixed.sub_queries


def test_a_one_sentence_question_gets_no_sentence_queries() -> None:
    assert question_sentences("How long do eggs keep in the fridge?") == []
    assert question_sentences("Tell me about salt. And sugar.") == []  # no question sentence
