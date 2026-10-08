"""Phase 2 exit criteria, checked on the real downloaded corpus.

corpus/raw/ is not committed, so these tests skip when a file is missing.
Run them after `python -m guidance_rag.ingest fetch`; deselect with `-m "not corpus"`.
"""

import re
from functools import cache

import pymupdf
import pytest

from guidance_rag.ingest.fetch import DEFAULT_RAW_DIR
from guidance_rag.ingest.parse import parse_document
from guidance_rag.ingest.parse_pdf import default_ocr_engine
from guidance_rag.ingest.tree import Document, iter_sections, walk
from guidance_rag.models import BlockType, DocumentFormat
from guidance_rag.registry import load_registry

pytestmark = pytest.mark.corpus

REGISTRY = load_registry()
DOCS = REGISTRY.included
PDF_DOCS = [d for d in DOCS if d.format is DocumentFormat.PDF]


@cache
def tree(doc_id: str) -> Document:
    doc = REGISTRY.get(doc_id)
    if not (DEFAULT_RAW_DIR / doc.raw_filename).exists():
        pytest.skip(f"{doc.raw_filename} not downloaded; run: python -m guidance_rag.ingest fetch")
    return parse_document(doc)


def test_dgi_lists_every_numbered_guideline_from_its_contents_page() -> None:
    parsed = tree("icmr-nin-dgi-2024")
    with pymupdf.open(DEFAULT_RAW_DIR / "icmr-nin-dgi-2024.pdf") as pdf:
        contents = pdf[7].get_text() + pdf[8].get_text()  # the two CONTENTS pages
    expected = {int(n) for n in re.findall(r"GUIDELINE\s*(\d+)", contents)}
    assert expected == set(range(1, 18))

    guidelines = {}
    for section in parsed.sections:
        if m := re.match(r"GUIDELINE (\d+) (\S.*)", section.heading):
            guidelines[int(m.group(1))] = (m.group(2), section)
    assert set(guidelines) == expected
    for number, (title, section) in guidelines.items():
        assert len(title) > 10, f"guideline {number} has no title"
        kinds = [b.type for b in section.blocks]
        assert kinds[:1] == [BlockType.RECOMMENDATION], f"guideline {number} has no RATIONALE"


def test_dgi_rationale_and_points_to_register_are_recommendation_blocks() -> None:
    recs = [
        b.text for _, _, b in walk(tree("icmr-nin-dgi-2024")) if b.type is BlockType.RECOMMENDATION
    ]
    assert sum(t.startswith("RATIONALE") for t in recs) == 17
    assert sum(t.startswith("POINTS TO REGISTER") for t in recs) == 17
    salt = next(t for t in recs if t.startswith("POINTS TO REGISTER") and "iodized salt" in t)
    assert "maximum of 5g per day" in salt


def test_dgi_table_merged_cells_are_expanded() -> None:
    (table,) = [
        b.table
        for _, _, b in walk(tree("icmr-nin-dgi-2024"))
        if b.table and b.table.caption and b.table.caption.startswith("Table 1.6.")
    ]
    assert table.header_rows[0][:3] == ["Age group", "Category of work", "Body wt"]
    assert table.rows[1][:3] == ["Men", "Moderate", "65"]  # "Men" and "65" span down
    assert table.rows[4][:3] == ["Pregnant women", "Pregnant women", "55+10"]  # spans across


def test_foodsafety_chart_is_one_table_with_its_header_row() -> None:
    tables = [b.table for _, _, b in walk(tree("foodsafety-cold-storage")) if b.table]
    assert len(tables) == 1
    (header,) = tables[0].header_rows
    assert header[0] == "Food" and header[2].startswith("Refrigerator")
    assert ["Hot dogs", "Unopened package", "2 weeks", "1 to 2 months"] in tables[0].rows


def test_who_outline_has_the_nutrient_guidance_sections() -> None:
    paths = [p for p, _ in iter_sections(tree("who-healthy-diet"))]
    assert ["Healthy diet", "WHO guidance on healthy diets", "Salt/sodium and potassium"] in paths


def test_jecfa_outline_comes_from_bookmarks_without_reference_lists() -> None:
    headings = [s.heading for _, s in iter_sections(tree("jecfa-trs-1058"))]
    assert "3.1.4 Carob bean gum" in headings
    assert not [h for h in headings if h.lower().startswith("reference")]


def test_raised_zero_degree_signs_read_as_degrees() -> None:
    text = " ".join(b.text for _, _, b in walk(tree("fssai-fsms-poultry")))
    assert "chilled at or below 4°C" in text
    assert "below 40C" not in text


def test_milk_transport_temperatures_use_the_hand_corrected_table() -> None:
    (table,) = [
        b.table
        for _, _, b in walk(tree("fssai-fsms-milk"))
        if b.table and b.table.table_id == "p29-t1"
    ]
    assert table.rows[0] == [
        "At plant",
        "-18 °C",
        "4 to 8 °C",
        "4 to 8 °C",
        "Below -18 °C",
        "<5 °C",
        "Ambient Temperature",
    ]


def test_scanned_milk_checklist_is_ocred() -> None:
    if default_ocr_engine() is None:
        pytest.skip("OCR extra not installed: uv sync --extra ocr")
    ocr = [b for _, _, b in walk(tree("fssai-fsms-milk")) if b.ocr]
    assert {b.page for b in ocr} == {74, 75}
    assert any("4°C or lower" in b.text for b in ocr)


# Running headers/footers as printed in each PDF (checked by hand in 1.5).
RUNNING_TEXT = {
    "icmr-nin-dgi-2024": ["ICMR-National Institute of Nutrition Dietary Guidelines for Indians"],
    "jecfa-trs-1058": [
        "WHO Technical Report Series, No. 1058",
        "Joint FAO/WHO Expert Committee on Food Additives One-hundredth report",
    ],
    "fssai-fsms-poultry": ["| Page", "P a g e"],
}


@pytest.mark.parametrize("doc_id", [d.doc_id for d in PDF_DOCS])
def test_no_running_headers_or_page_numbers_remain(doc_id: str) -> None:
    for _, _, block in walk(tree(doc_id)):
        if block.table:
            continue
        for running in RUNNING_TEXT.get(doc_id, []):
            assert running not in block.text, (block.page, block.text[:80])
        assert not re.fullmatch(r"\d{1,3}", block.text.strip()), (block.page, block.text)


@pytest.mark.parametrize("doc_id", [d.doc_id for d in PDF_DOCS])
def test_no_table_text_in_paragraphs(doc_id: str) -> None:
    blocks = [b for _, _, b in walk(tree(doc_id))]
    for table_block in [b for b in blocks if b.table]:
        assert table_block.table is not None
        pages = {table_block.page, table_block.page_end or table_block.page}
        prose = " ".join(b.text for b in blocks if not b.table and b.page in pages)
        long_cells = {c for row in table_block.table.rows for c in row if len(c) > 25}
        leaked = [c for c in long_cells if c in prose]
        assert not leaked, f"{table_block.table.table_id}: {leaked[:3]}"


@pytest.mark.parametrize("doc_id", [d.doc_id for d in DOCS])
def test_blocks_are_non_empty_and_pdf_blocks_have_pages(doc_id: str) -> None:
    is_pdf = REGISTRY.get(doc_id).format is DocumentFormat.PDF
    for path, _, block in walk(tree(doc_id)):
        assert block.text.strip(), path
        assert all(h.strip() for h in path)
        assert (block.page is not None) == is_pdf
