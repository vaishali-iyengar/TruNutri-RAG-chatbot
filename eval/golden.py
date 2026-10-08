"""Golden test set: schema and loader for eval/golden.yaml.

The golden set defines what "done" means for the whole system (ARCHITECTURE.md §11.1).
Each entry says which status the assistant should return and, for answerable
questions, which documents it should cite.
"""

from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from guidance_rag.models import AnswerStatus, RefusalCategory
from guidance_rag.registry import load_registry

GOLDEN_PATH = Path(__file__).resolve().parent / "golden.yaml"

# Questions may only expect documents that are in the corpus.
KNOWN_DOC_IDS: frozenset[str] = frozenset(d.doc_id for d in load_registry().included)


class GoldenCategory(StrEnum):
    SINGLE_DOC = "single_doc"
    TABLE_LOOKUP = "table_lookup"
    RECOMMENDATION = "recommendation"
    DOC_FILTERED = "doc_filtered"
    CROSS_DOC = "cross_doc"
    NOT_IN_CORPUS = "not_in_corpus"
    UNKNOWN_DOC = "unknown_doc"
    OUT_OF_SCOPE = "out_of_scope"
    NEAR_MISS = "near_miss"


ANSWERABLE_CATEGORIES = frozenset(
    {
        GoldenCategory.SINGLE_DOC,
        GoldenCategory.TABLE_LOOKUP,
        GoldenCategory.RECOMMENDATION,
        GoldenCategory.DOC_FILTERED,
        GoldenCategory.CROSS_DOC,
        GoldenCategory.NEAR_MISS,
    }
)

OUT_OF_SCOPE_REFUSALS = frozenset(
    {
        RefusalCategory.MEDICAL,
        RefusalCategory.CALORIE_TARGET,
        RefusalCategory.BODY_WEIGHT,
    }
)


class GoldenEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z]{2}-\d{2}$")
    question: str = Field(min_length=5)
    category: GoldenCategory
    doc_filter: list[str] | None = None
    expected_status: AnswerStatus
    expected_refusal: RefusalCategory | None = None
    expected_doc_ids: list[str] = Field(default_factory=list)
    expected_answer_notes: str = ""
    # True once expected_answer_notes has been checked against the source document.
    verified: bool = False
    # Chunks in corpus/chunks/ that contain the answer (Phase 3, sub-task 3.9).
    gold_chunk_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Held out for the final score (9.1): not looked at while tuning or fixing.
    holdout: bool = False

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        unknown = (set(self.expected_doc_ids) | set(self.doc_filter or [])) - KNOWN_DOC_IDS
        if unknown:
            raise ValueError(f"unknown doc_ids: {sorted(unknown)}")

        if self.category in ANSWERABLE_CATEGORIES:
            if self.expected_status not in (AnswerStatus.ANSWERED, AnswerStatus.PARTIAL):
                raise ValueError(f"{self.category} questions must expect an answer")
            if not self.expected_doc_ids:
                raise ValueError("answerable questions need expected_doc_ids")
            if self.expected_refusal is not None:
                raise ValueError("answerable questions must not set expected_refusal")
            if not self.expected_answer_notes:
                raise ValueError("answerable questions need expected_answer_notes")

        if self.category is GoldenCategory.CROSS_DOC and len(set(self.expected_doc_ids)) < 2:
            raise ValueError("cross_doc questions need at least 2 expected_doc_ids")

        if self.category is GoldenCategory.DOC_FILTERED:
            if not self.doc_filter:
                raise ValueError("doc_filtered questions need a doc_filter")
            if not set(self.expected_doc_ids) <= set(self.doc_filter):
                raise ValueError("expected_doc_ids must be inside doc_filter")

        if self.category in (GoldenCategory.NOT_IN_CORPUS, GoldenCategory.UNKNOWN_DOC):
            expected = RefusalCategory(self.category.value)
            if self.expected_status is not AnswerStatus.NOT_IN_CORPUS:
                raise ValueError(f"{self.category} questions must expect not_in_corpus")
            if self.expected_refusal is not expected:
                raise ValueError(f"{self.category} questions must expect refusal {expected}")
            if self.expected_doc_ids:
                raise ValueError("refused questions must not list expected_doc_ids")

        if self.category is GoldenCategory.OUT_OF_SCOPE:
            if self.expected_status is not AnswerStatus.OUT_OF_SCOPE:
                raise ValueError("out_of_scope questions must expect out_of_scope")
            if self.expected_refusal not in OUT_OF_SCOPE_REFUSALS:
                raise ValueError("out_of_scope questions need an out-of-scope refusal category")
            if self.expected_doc_ids:
                raise ValueError("refused questions must not list expected_doc_ids")

        return self


class GoldenSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    questions: list[GoldenEntry]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [q.id for q in self.questions]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate golden ids: {duplicates}")
        return self

    def by_category(self, category: GoldenCategory) -> list[GoldenEntry]:
        return [q for q in self.questions if q.category is category]


def load_golden(path: Path = GOLDEN_PATH) -> GoldenSet:
    with path.open(encoding="utf-8") as f:
        return GoldenSet.model_validate(yaml.safe_load(f))
