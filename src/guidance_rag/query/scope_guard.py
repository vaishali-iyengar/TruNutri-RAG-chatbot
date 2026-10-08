"""Scope guard: deterministic out-of-scope refusal (implementation-plan.md, Phase 5; §7.2).

The guard runs before retrieval and any LLM call, so a refusal can't be talked around
by prompt injection. It refuses four kinds of question:

- MEDICAL: diagnosis, treatment, medication, or a person's own condition.
- CALORIE_TARGET: personal calorie targets and calorie-based plans.
- BODY_WEIGHT: weight goals, BMI, weight-loss targets.
- NUTRIENT_LOOKUP: nutrient values of a single food (Milestone 3, not this assistant).

What the guidance says about populations stays in scope: "What does WHO say about salt
and blood pressure?" is answered.

The rules are data (scope_rules.yaml). A rule fires when its pattern matches the
normalised question and so does every pattern in `requires`. `check_output` applies the
output rules to drafted claims and removes personal numeric targets.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from guidance_rag.models import DocAnswer, RefusalCategory

DEFAULT_RULES_PATH = Path(__file__).with_name("scope_rules.yaml")


class ScopeCategory(StrEnum):
    """Out-of-scope categories, in priority order (values match RefusalCategory)."""

    MEDICAL = "medical"
    CALORIE_TARGET = "calorie_target"
    BODY_WEIGHT = "body_weight"
    NUTRIENT_LOOKUP = "nutrient_lookup"

    @property
    def refusal(self) -> RefusalCategory:
        return RefusalCategory(self.value)


@dataclass(frozen=True)
class Rule:
    id: str
    category: ScopeCategory
    pattern: re.Pattern[str]
    requires: tuple[re.Pattern[str], ...] = ()  # all must match too
    note: str = ""

    def fires(self, text: str) -> bool:
        return bool(self.pattern.search(text)) and all(r.search(text) for r in self.requires)


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    category: ScopeCategory | None = None
    matched_rule: str | None = None


@dataclass(frozen=True)
class RemovedClaim:
    doc_id: str
    text: str
    category: ScopeCategory
    rule: str


@dataclass(frozen=True)
class OutputCheck:
    sections: list[DocAnswer]  # what is left; sections with no claims left are dropped
    removed: list[RemovedClaim] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        """Every claim was removed: the answer becomes an out-of-scope refusal."""
        return bool(self.removed) and not self.sections

    @property
    def category(self) -> ScopeCategory | None:
        return self.removed[0].category if self.removed else None


# --- Normalisation -------------------------------------------------------------------

# Common misspellings of the words the rules look for.
MISSPELLINGS = {
    "calores": "calories",
    "calroies": "calories",
    "caloreis": "calories",
    "calaries": "calories",
    "colories": "calories",
    "calorise": "calories",
    "protien": "protein",
    "protine": "protein",
    "wieght": "weight",
    "weigth": "weight",
    "wight": "weight",
    "diabetis": "diabetes",
    "diabeties": "diabetes",
    "diabtes": "diabetes",
    "diebetes": "diabetes",
    "colesterol": "cholesterol",
    "cholestrol": "cholesterol",
    "cholesteral": "cholesterol",
    "presure": "pressure",
    "preassure": "pressure",
    "medecine": "medicine",
    "medicin": "medicine",
    "medcine": "medicine",
}
_MISSPELLING = re.compile(r"\b(" + "|".join(MISSPELLINGS) + r")\b")
# Right/left single quotation marks, modifier apostrophe, backtick -> "'"
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "`": "'"})


def normalise(text: str) -> str:
    """Lowercase, Unicode NFKC, straight apostrophes, underscores as spaces, collapsed
    whitespace, and common misspellings fixed ("calores" -> "calories")."""
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).lower()
    # Underscores join words into one \w token ("daily_calories"), hiding them from \b.
    text = re.sub(r"[\s_]+", " ", text).strip()
    return _MISSPELLING.sub(lambda m: MISSPELLINGS[m.group(1)], text)


# --- Rules -------------------------------------------------------------------------------

_TERM = re.compile(r"\{([a-z_]+)\}")


def _expand(pattern: str, terms: dict[str, list[str]]) -> str:
    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in terms:
            raise ValueError(f"unknown term {{{name}}} in {pattern!r}")
        return "(?:" + "|".join(terms[name]) + ")"

    return _TERM.sub(sub, pattern)


def _parse_rules(entries: list[dict[str, Any]], terms: dict[str, list[str]]) -> list[Rule]:
    rules = []
    for entry in entries:
        requires = entry.get("requires") or []
        if isinstance(requires, str):
            requires = [requires]
        try:
            rules.append(
                Rule(
                    id=entry["id"],
                    category=ScopeCategory(entry["category"]),
                    pattern=re.compile(_expand(entry["pattern"], terms)),
                    requires=tuple(re.compile(_expand(r, terms)) for r in requires),
                    note=entry.get("note", ""),
                )
            )
        except re.error as exc:
            raise ValueError(f"rule {entry.get('id')}: invalid regex: {exc}") from exc
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate rule ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    return rules


def _load(path: Path) -> tuple[list[Rule], list[Rule]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms = {k: [str(t) for t in v] for k, v in (data.get("terms") or {}).items()}
    return (
        _parse_rules(data.get("rules") or [], terms),
        _parse_rules(data.get("output_rules") or [], terms),
    )


def load_rules(path: Path = DEFAULT_RULES_PATH) -> list[Rule]:
    """The input rules, in priority order."""
    return _load(path)[0]


# --- Guard -----------------------------------------------------------------------------


class ScopeGuard:
    def __init__(
        self, rules: Sequence[Rule] | None = None, output_rules: Sequence[Rule] | None = None
    ) -> None:
        if rules is None or output_rules is None:
            default_in, default_out = _load(DEFAULT_RULES_PATH)
            rules = default_in if rules is None else rules
            output_rules = default_out if output_rules is None else output_rules
        self.rules = list(rules)
        self.output_rules = list(output_rules)

    def check_input(self, question: str) -> GuardResult:
        """Refuse when the first rule (in priority order) fires."""
        text = normalise(question)
        for rule in self.rules:
            if rule.fires(text):
                return GuardResult(False, rule.category, rule.id)
        return GuardResult(True)

    def check_output(self, sections: Sequence[DocAnswer]) -> OutputCheck:
        """Remove claims that give the reader a personal numeric target (kcal, kg, BMI)."""
        kept: list[DocAnswer] = []
        removed: list[RemovedClaim] = []
        for section in sections:
            claims = []
            for claim in section.claims:
                text = normalise(claim.text)
                rule = next((r for r in self.output_rules if r.fires(text)), None)
                if rule:
                    removed.append(RemovedClaim(section.doc_id, claim.text, rule.category, rule.id))
                else:
                    claims.append(claim)
            if claims:
                kept.append(section if len(claims) == len(section.claims) else
                            section.model_copy(update={"claims": claims}))  # fmt: skip
        return OutputCheck(kept, removed)


@cache
def default_guard() -> ScopeGuard:
    return ScopeGuard()


def check_input(question: str) -> GuardResult:
    return default_guard().check_input(question)


def check_output(sections: Sequence[DocAnswer]) -> OutputCheck:
    return default_guard().check_output(sections)
