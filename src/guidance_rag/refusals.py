"""Refusal messages, built in code, never by the LLM (ARCHITECTURE.md §7.2; plan 5.4).

Out-of-scope refusals (Phase 5) are fixed templates. Not-in-corpus refusals list the
documents searched (a first version for Phase 6; Phase 7.3 finalises the wording).
"""

from collections.abc import Sequence

from guidance_rag.models import Refusal, RefusalCategory, SourceDocument

_ONLY_GUIDANCE = (
    "This assistant only reports what public dietary and food-safety guidance documents say."
)
_REFERRAL = (
    "For advice about your own health, please speak to a registered dietitian or your doctor."
)

SCOPE_MESSAGES: dict[RefusalCategory, str] = {
    RefusalCategory.MEDICAL: (
        "I can't give personal health advice, such as about a health condition, "
        f"medication, or your own pregnancy or breastfeeding. {_ONLY_GUIDANCE} {_REFERRAL}"
    ),
    RefusalCategory.CALORIE_TARGET: (
        "I can't set personal calorie targets or calorie-based meal plans. "
        f"{_ONLY_GUIDANCE} {_REFERRAL}"
    ),
    RefusalCategory.BODY_WEIGHT: (
        "I can't advise on personal body-weight goals, BMI or weight-loss targets. "
        f"{_ONLY_GUIDANCE} {_REFERRAL}"
    ),
    RefusalCategory.NUTRIENT_LOOKUP: (
        "I can't look up nutrient values for individual foods, such as the calories or "
        "protein in a serving: this assistant covers written dietary and food-safety "
        "guidance, not nutrient composition data. I can tell you what the guidance "
        "documents say about a food or nutrient in general."
    ),
}

# Categories whose refusal refers the person to a professional (§7.1).
REFERRAL_CATEGORIES = frozenset(
    {RefusalCategory.MEDICAL, RefusalCategory.CALORIE_TARGET, RefusalCategory.BODY_WEIGHT}
)


def scope_refusal(category: RefusalCategory) -> Refusal:
    """The fixed refusal for an out-of-scope category."""
    if category not in SCOPE_MESSAGES:
        raise ValueError(f"not an out-of-scope category: {category}")
    return Refusal(category=category, message=SCOPE_MESSAGES[category])


def describe(doc: SourceDocument) -> str:
    """ "Title (Publisher, Year)" for a refusal message."""
    return f"{doc.title} ({doc.publisher}, {doc.year})"


def not_in_corpus_refusal(searched: Sequence[SourceDocument]) -> Refusal:
    """The guidance doesn't cover the question; names every document searched."""
    listed = "; ".join(describe(d) for d in searched)
    return Refusal(
        category=RefusalCategory.NOT_IN_CORPUS,
        message=f"The guidance documents I searched don't cover this question. Searched: {listed}.",
    )


def unknown_doc_refusal(sources: Sequence[str], available: Sequence[SourceDocument]) -> Refusal:
    """The question names a source that isn't in the corpus; lists what is."""
    named = ", ".join(sources) or "That document"
    listed = "; ".join(describe(d) for d in available)
    return Refusal(
        category=RefusalCategory.UNKNOWN_DOC,
        message=(
            f"{named} isn't in my corpus, so I can't say what it recommends. "
            f"I can search: {listed}."
        ),
    )
