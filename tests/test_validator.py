"""Citation validator and support check (implementation-plan.md, 6.4-6.5), no LLM needed."""

import pytest

from guidance_rag.models import Claim, DocAnswer
from guidance_rag.validator import numbers, support_problem, validate
from tests.fakes import CHUNKS, DGI_OILS, FRIDGE_POULTRY, WHO_FATS, WHO_SALT, evidence

EVIDENCE = evidence(FRIDGE_POULTRY, WHO_SALT, DGI_OILS)


def section(doc_id: str, *claims: tuple[str, list[str]]) -> DocAnswer:
    return DocAnswer(doc_id=doc_id, claims=[Claim(text=t, chunk_ids=c) for t, c in claims])


def test_a_supported_claim_is_kept() -> None:
    result = validate(
        [
            section(
                "foodsafety-cold-storage",
                ("Fresh chicken pieces keep 1 to 2 days in the refrigerator.", [FRIDGE_POULTRY]),
            )
        ],
        EVIDENCE,
    )

    assert result.claim_count == 1 and result.dropped == []


def test_a_claim_without_a_citation_is_dropped() -> None:
    result = validate([section("who-healthy-diet", ("Limit salt.", []))], EVIDENCE)

    assert result.sections == [] and result.dropped[0].reason == "no citation"


def test_a_claim_citing_an_invented_chunk_is_dropped() -> None:
    result = validate(
        [section("who-healthy-diet", ("Limit salt to 5 g.", ["who-healthy-diet:made-up:1"]))],
        EVIDENCE,
    )

    assert result.dropped[0].reason == "cites a chunk that wasn't retrieved"


def test_a_claim_citing_a_chunk_that_exists_but_was_not_retrieved_is_dropped() -> None:
    result = validate(
        [section("who-healthy-diet", ("Prefer unsaturated oils.", [WHO_FATS]))], EVIDENCE
    )

    assert result.dropped[0].reason == "cites a chunk that wasn't retrieved"


def test_a_claim_citing_another_documents_chunk_is_dropped() -> None:
    """The "never blend sources" check: an ICMR section can't cite a WHO chunk."""
    result = validate(
        [
            section(
                "icmr-nin-dgi-2024",
                ("Salt intake should be limited to less than 5 grams per day.", [WHO_SALT]),
            )
        ],
        EVIDENCE,
    )

    assert result.dropped[0].reason == "cites another document's chunk"


def test_a_claim_mixing_its_own_and_another_documents_chunk_is_dropped() -> None:
    result = validate(
        [
            section(
                "who-healthy-diet",
                ("Salt intake should be limited to less than 5 grams.", [WHO_SALT, DGI_OILS]),
            )
        ],
        EVIDENCE,
    )

    assert result.dropped[0].reason == "cites another document's chunk"


def test_a_claim_with_a_number_missing_from_its_chunk_is_dropped() -> None:
    """Plan 6.5: "5 days" is dropped when the chunk says "1 to 2 days"."""
    result = validate(
        [
            section(
                "foodsafety-cold-storage",
                ("Fresh chicken pieces keep 5 days in the refrigerator.", [FRIDGE_POULTRY]),
            )
        ],
        EVIDENCE,
    )

    assert result.dropped[0].reason == "numbers not in the cited text: 5"


def test_a_claim_unrelated_to_its_chunk_is_dropped() -> None:
    result = validate(
        [
            section(
                "who-healthy-diet",
                ("Infants should be breastfed exclusively for six months.", [WHO_SALT]),
            )
        ],
        EVIDENCE,
    )

    assert "numbers not in the cited text" in result.dropped[0].reason or (
        "too few key words" in result.dropped[0].reason
    )


def test_kept_and_dropped_claims_are_separated_per_section() -> None:
    result = validate(
        [
            section(
                "who-healthy-diet",
                ("Adult salt intake should be limited to less than 5 grams per day.", [WHO_SALT]),
                ("Adult salt intake should be limited to 9 grams per day.", [WHO_SALT]),
            ),
            section("icmr-nin-dgi-2024", ("Oils.", [])),
        ],
        EVIDENCE,
    )

    assert [(s.doc_id, len(s.claims)) for s in result.sections] == [("who-healthy-diet", 1)]
    assert len(result.dropped) == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 to 2 days", {"1", "2"}),
        ("3–4 days", {"3", "4"}),
        ("1,800 kcal", {"1800"}),
        ("five grams", {"5"}),
        ("4.0 °C", {"4"}),
        ("Guideline 11", {"11"}),
    ],
)
def test_numbers(text: str, expected: set[str]) -> None:
    assert numbers(text) == expected


def test_spelled_out_numbers_in_the_chunk_support_digits_in_the_claim() -> None:
    chunk = CHUNKS[WHO_SALT].model_copy(
        update={"text": "Limit salt to less than five grams a day."}
    )

    assert (
        support_problem(Claim(text="Limit salt to less than 5 g a day.", chunk_ids=[]), [chunk])
        is None
    )


def test_a_number_must_come_from_the_matching_table_row() -> None:
    """The chart chunk has "3 to 5 days" in another row; chicken's row says "1 to 2 days"."""
    assert "5" in CHUNKS[FRIDGE_POULTRY].text
    claim = Claim(text="Fresh chicken pieces keep 5 days in the refrigerator.", chunk_ids=[])

    assert support_problem(claim, [CHUNKS[FRIDGE_POULTRY]]) == "numbers not in the cited text: 5"


def test_numbers_from_the_table_header_still_count() -> None:
    claim = Claim(
        text="Fresh chicken pieces keep 1 to 2 days in a refrigerator at 40°F (4°C) or below.",
        chunk_ids=[],
    )

    assert support_problem(claim, [CHUNKS[FRIDGE_POULTRY]]) is None


def test_a_claim_combining_two_rows_is_kept() -> None:
    claim = Claim(
        text="Fresh whole chicken keeps 1 year in the freezer and chicken pieces 9 months.",
        chunk_ids=[],
    )

    assert support_problem(claim, [CHUNKS[FRIDGE_POULTRY]]) is None


@pytest.mark.parametrize(
    ("chunk_id", "text"),
    [
        # Real claims from gpt-oss-120b that combine two bullets of one passage (6.8).
        (
            "icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:4",
            "Take iron-folic acid (IFA) tablets after 12 weeks of pregnancy and continue them"
            " during lactation; a daily folic acid supplement of 500 µg (0.5 mg) is advised"
            " during the first trimester.",
        ),
        (
            "fssai-fsms-poultry:sanitary-hygienic-requirements-for-small-slaught:1",
            "The facility must be designed with three separate sections: Holding Area, Slaughter"
            " Area, and Portioning & Retail Area.",
        ),
        (
            "fssai-fsms-poultry:10-quality-control:1",
            "A quality control programme must include periodic microbiological examination, with"
            " testing at least once every six months.",
        ),
    ],
)
def test_prose_claims_combining_two_bullets_keep_their_numbers(chunk_id: str, text: str) -> None:
    """Row matching applies to table rows only; prose is checked as a whole."""
    assert support_problem(Claim(text=text, chunk_ids=[chunk_id]), [CHUNKS[chunk_id]]) is None
