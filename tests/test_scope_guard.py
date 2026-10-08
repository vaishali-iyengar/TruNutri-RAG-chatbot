"""Scope guard (implementation-plan.md, Phase 5; ARCHITECTURE.md §7.2).

The case table is tests/data/scope_cases.yaml. Phase 5 exit criteria: 100% of the
refuse cases refused by the rules alone, and >= 95% of the answer cases let through.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

from eval.golden import GoldenCategory, load_golden
from guidance_rag.models import AnswerStatus, Claim, DocAnswer
from guidance_rag.pipeline import Draft, Pipeline
from guidance_rag.query.scope_guard import (
    GuardResult,
    Rule,
    ScopeCategory,
    ScopeGuard,
    check_input,
    check_output,
    load_rules,
    normalise,
)
from tests.test_models import CHUNK

CASES: dict[str, Any] = yaml.safe_load(
    (Path(__file__).parent / "data" / "scope_cases.yaml").read_text(encoding="utf-8")
)
REFUSE = [(c["q"], ScopeCategory(c["category"])) for c in CASES["refuse"]]
ANSWER: list[str] = CASES["answer"]


# --- Rule engine core (5.2) ----------------------------------------------------------


def test_normalise() -> None:
    assert normalise("  How   MANY\tCalores?  ") == "how many calories?"
    assert normalise("I\u2019m  diabetic") == "i'm diabetic"  # curly apostrophe
    full_width = "".join(chr(ord(c) + 0xFEE0) for c in "CALORIES")
    assert normalise(full_width) == "calories"  # NFKC folds full-width letters
    assert normalise("protien and wieght") == "protein and weight"


def test_a_rule_fires_only_when_its_requires_pattern_also_matches() -> None:
    rule = Rule(
        id="fake",
        category=ScopeCategory.MEDICAL,
        pattern=re.compile(r"\bblood pressure\b"),
        requires=(re.compile(r"\bmy\b"),),
    )
    guard = ScopeGuard([rule])

    assert guard.check_input("What does WHO say about blood pressure?") == GuardResult(True)
    assert guard.check_input("Lower my blood pressure") == GuardResult(
        False, ScopeCategory.MEDICAL, "fake"
    )


def test_rules_load_from_the_data_file_in_priority_order() -> None:
    rules = load_rules()
    categories = [r.category for r in rules]

    assert len({r.id for r in rules}) == len(rules)  # unique ids
    assert set(categories) == set(ScopeCategory)
    # Medical first, nutrient lookups last: a question that is both gets the stronger refusal.
    assert categories == sorted(categories, key=list(ScopeCategory).index)


def test_an_unknown_term_in_a_rule_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("terms: {}\nrules:\n  - {id: x, category: medical, pattern: '{nope}'}\n")

    with pytest.raises(ValueError, match="nope"):
        load_rules(path)


# --- Rule sets against the case table (5.1, 5.3) ------------------------------------


@pytest.mark.parametrize(("question", "category"), REFUSE, ids=[q for q, _ in REFUSE])
def test_should_refuse(question: str, category: ScopeCategory) -> None:
    result = check_input(question)

    assert not result.allowed, "not refused"
    assert result.category is category, f"refused as {result.category} by {result.matched_rule}"


def test_case_table_size() -> None:
    assert len(REFUSE) >= 60 and len(ANSWER) >= 30


def test_should_answer_pass_rate() -> None:
    """>= 95% of the should-answer cases pass (exit criterion); list any that don't."""
    blocked = {q: check_input(q).matched_rule for q in ANSWER if not check_input(q).allowed}
    assert len(blocked) <= len(ANSWER) * 0.05, blocked


@pytest.mark.parametrize("question", ANSWER)
def test_should_answer(question: str) -> None:
    result = check_input(question)
    assert result.allowed, f"refused as {result.category} by {result.matched_rule}"


def test_golden_set() -> None:
    """Out-of-scope golden questions are refused with their category; all others pass."""
    for q in load_golden().questions:
        result = check_input(q.question)
        if q.category is GoldenCategory.OUT_OF_SCOPE:
            assert q.expected_refusal is not None
            assert result.category == ScopeCategory(q.expected_refusal.value), q.id
        else:
            assert result.allowed, (q.id, result.matched_rule)


# --- Output guard (5.5) ---------------------------------------------------------------


def answer(*claims: str, doc_id: str = "icmr-nin-dgi-2024") -> list[DocAnswer]:
    return [
        DocAnswer(
            doc_id=doc_id,
            claims=[Claim(text=t, chunk_ids=[f"{doc_id}:x:{i}"]) for i, t in enumerate(claims)],
        )
    ]


def test_output_guard_removes_a_personal_calorie_target() -> None:
    sections = answer(
        "Adults should limit salt to less than 5 g per day.",
        "So you should eat 1,800 kcal a day.",
    )

    result = check_output(sections)

    assert [c.text for d in result.sections for c in d.claims] == [
        "Adults should limit salt to less than 5 g per day."
    ]
    assert [(r.text, r.category) for r in result.removed] == [
        ("So you should eat 1,800 kcal a day.", ScopeCategory.CALORIE_TARGET)
    ]
    assert not result.refused


def test_output_guard_keeps_population_figures() -> None:
    sections = answer(
        "A sedentary adult man needs about 2,080 kcal a day.",
        "Weight-reduction diets should not go below 1,000 kcal per day.",
    )

    result = check_output(sections)

    assert result.sections == sections and not result.removed


def test_output_guard_removes_weight_targets_and_drops_empty_sections() -> None:
    sections = answer("You should weigh about 60 kg.", doc_id="who-healthy-diet") + answer(
        "Use a combination of oils."
    )

    result = check_output(sections)

    assert [d.doc_id for d in result.sections] == ["icmr-nin-dgi-2024"]
    assert result.removed[0].category is ScopeCategory.BODY_WEIGHT


def test_when_every_claim_is_removed_the_answer_is_refused() -> None:
    result = check_output(answer("Your target is 1500 kcal.", "You can lose 5 kg a month."))

    assert result.sections == []
    assert result.refused
    assert result.category is ScopeCategory.CALORIE_TARGET  # the first removed claim's


# --- "Nothing else runs" (5.6) ---------------------------------------------------------


def downstream() -> tuple[Mock, Mock, Pipeline]:
    """A pipeline whose answer step calls a mock retriever and a mock LLM client."""
    retriever, llm = Mock(name="retriever"), Mock(name="llm")

    def answer_step(question: str, doc_filter: Sequence[str] | None) -> Draft:
        evidence = retriever.retrieve(question, doc_filter)
        llm.generate(question, evidence)
        sections = answer("Use a combination of oils.", "So you should eat 1,800 kcal a day.")
        chunks = {
            c: CHUNK.model_copy(update={"chunk_id": c})
            for s in sections
            for claim in s.claims
            for c in claim.chunk_ids
        }
        return Draft(sections, chunks, ["icmr-nin-dgi-2024"], ["icmr-nin-dgi-2024"])

    return retriever, llm, Pipeline(answer_step)


@pytest.mark.parametrize(("question", "category"), REFUSE[::8], ids=[q for q, _ in REFUSE[::8]])
def test_a_refused_question_never_reaches_retrieval_or_the_llm(
    question: str, category: ScopeCategory
) -> None:
    retriever, llm, pipeline = downstream()

    result = pipeline.run(question)

    retriever.retrieve.assert_not_called()
    llm.generate.assert_not_called()
    assert result.status is AnswerStatus.OUT_OF_SCOPE
    assert result.refusal is not None and result.refusal.category is category.refusal


def test_an_allowed_question_runs_and_its_answer_is_output_guarded() -> None:
    retriever, llm, pipeline = downstream()

    result = pipeline.run("What does WHO say about salt and blood pressure?")

    retriever.retrieve.assert_called_once()
    llm.generate.assert_called_once()
    assert result.status is AnswerStatus.ANSWERED
    assert [c.text for d in result.sections for c in d.claims] == ["Use a combination of oils."]
    assert [c.chunk_id for c in result.citations] == ["icmr-nin-dgi-2024:x:0"]  # renumbered
    assert result.markdown is not None and "1,800 kcal" not in result.markdown
