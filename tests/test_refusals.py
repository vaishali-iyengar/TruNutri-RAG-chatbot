"""Refusal templates (implementation-plan.md, 5.4)."""

import pytest

from guidance_rag.models import RefusalCategory
from guidance_rag.query.scope_guard import ScopeCategory
from guidance_rag.refusals import REFERRAL_CATEGORIES, SCOPE_MESSAGES, scope_refusal


@pytest.mark.parametrize("category", list(ScopeCategory))
def test_every_scope_category_has_a_template(category: ScopeCategory) -> None:
    refusal = scope_refusal(category.refusal)

    assert refusal.category is category.refusal
    assert refusal.message == SCOPE_MESSAGES[category.refusal]


def test_referral_templates_name_a_professional() -> None:
    assert {
        RefusalCategory.MEDICAL,
        RefusalCategory.CALORIE_TARGET,
        RefusalCategory.BODY_WEIGHT,
    } == REFERRAL_CATEGORIES
    for category in REFERRAL_CATEGORIES:
        message = SCOPE_MESSAGES[category]
        assert "registered dietitian" in message and "doctor" in message


def test_the_nutrient_lookup_template_explains_and_does_not_refer() -> None:
    message = SCOPE_MESSAGES[RefusalCategory.NUTRIENT_LOOKUP]

    assert "nutrient" in message and "doctor" not in message


def test_not_in_corpus_categories_are_not_scope_refusals() -> None:
    with pytest.raises(ValueError):
        scope_refusal(RefusalCategory.NOT_IN_CORPUS)
