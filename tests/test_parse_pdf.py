"""PDF parser tests on small PDFs generated with PyMuPDF.

Each generated page imitates a layout feature of the real corpus: running
headers and page numbers (all PDFs), numbered headings and "i." lists with
hanging lines (FSSAI), ruled tables that continue across pages (FSSAI HACCP
plans), two columns, pull quotes and RATIONALE boxes (DGI 2024), bookmarks
(JECFA) and a scanned page (FSSAI Milk checklist).
"""

from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

from guidance_rag.ingest.parse_pdf import OcrBox, _expand_merged, _span_text, parse_pdf
from guidance_rag.ingest.tree import Document, iter_sections, outline, walk
from guidance_rag.models import BlockType, HeadingRule, HeadingSource, ParserConfig

BODY, HEAD = "helv", "hebo"  # Helvetica and Helvetica-Bold
FSSAI_HEADINGS = [
    HeadingRule(level=1, min_size=14, bold=True),
    HeadingRule(level=2, min_size=11, bold=True, pattern=r"^\d+(\.\d+)*\.?\s", nest_by_number=True),
]


class Writer:
    """Writes lines top-down on a page, like a word processor."""

    def __init__(self, page: pymupdf.Page, x: float = 60, y: float = 90) -> None:
        self.page, self.x, self.y = page, x, y

    def line(self, text: str, size: float = 11, bold: bool = False, x: float | None = None) -> None:
        self.page.insert_text(
            (x if x is not None else self.x, self.y),
            text,
            fontsize=size,
            fontname=HEAD if bold else BODY,
        )
        self.y += size * 1.3

    def gap(self, points: float = 10) -> None:
        self.y += points

    def table(self, rows: list[list[str]], widths: list[float], bold_header: bool = True) -> None:
        """A table with a ruled border around every cell."""
        height = 18
        for r, row in enumerate(rows):
            x = self.x
            for text, w in zip(row, widths, strict=True):
                self.page.draw_rect(pymupdf.Rect(x, self.y, x + w, self.y + height), width=0.6)
                font = HEAD if r == 0 and bold_header else BODY
                self.page.insert_text((x + 3, self.y + 12), text, fontsize=9, fontname=font)
                x += w
            self.y += height
        self.y += 14


def decorate(page: pymupdf.Page, number: int) -> None:
    """Running header and page number, as on every FSSAI page."""
    page.insert_text((60, 40), "FSMS Guidance Document - Milk", fontsize=9, fontname=BODY)
    page.insert_text((290, 815), str(number), fontsize=9, fontname=BODY)


def build(tmp_path: Path, *pages: Callable[[pymupdf.Page], None], decorated: bool = False) -> Path:
    """Write a PDF with one page per drawing function; `decorated` adds a running
    header and page number to every page."""
    doc = pymupdf.open()
    for n, draw in enumerate(pages, start=1):
        page = doc.new_page(width=595, height=842)
        if decorated:
            decorate(page, n)
        draw(page)
    path = tmp_path / "doc.pdf"
    doc.save(path)
    return path


def parse(path: Path, **config: object) -> Document:
    return parse_pdf(
        path,
        doc_id="doc",
        title="Doc",
        config=ParserConfig.model_validate(config),
        ocr_engine=None,
    )


def texts(tree: Document, kind: BlockType | None = None) -> list[str]:
    return [b.text for _, _, b in walk(tree) if kind is None or b.type is kind]


# --- A small FSSAI-like document ------------------------------------------------------


def fssai_page_1(page: pymupdf.Page) -> None:
    w = Writer(page)
    w.line("A. OVERVIEW OF MILK INDUSTRY", 14, bold=True)
    w.gap()
    w.line("India has been the leading producer of dairy products since 1998 with")
    w.line("sustained growth in the availability of milk.")
    w.gap(12)
    w.line("Dairy activities form an essential part of the rural economy.")
    w.gap()
    w.line("1. Location and Surroundings", bold=True)
    for marker, first, more in [
        ("i.", "The facility shall be situated away from polluted areas like open", "drains."),
        ("ii.", "The site boundaries shall be clearly identified.", None),
    ]:
        y = w.y
        w.line(marker, x=64)  # the marker is a separate text run, as in the FSSAI PDFs
        w.y = y
        w.line(first, x=90)
        if more:
            w.line(more, x=64)  # a hanging line under the marker
    w.gap(14)
    w.line("Separate stores shall be provided for chemicals.")


def fssai_page_2(page: pymupdf.Page) -> None:
    w = Writer(page)
    w.line("2. Storage and Material Control", bold=True)
    w.line("2.1 Cold storage", bold=True)
    w.line("Table 2: Storage temperatures")
    w.gap(4)
    w.table(
        [
            ["Product", "Temp °C", "Remarks"],
            ["Pasteurised milk", "4 or less", "Chilled"],
            ["Ice cream", "-18", "Frozen"],
        ],
        [180, 100, 120],
    )


def fssai_page_3(page: pymupdf.Page) -> None:
    w = Writer(page)
    w.table(
        [["Product", "Temp °C", "Remarks"], ["Butter", "4 or less", "Chilled"]],
        [180, 100, 120],
    )
    w.line("Temperatures shall be recorded every shift.")
    w.gap()
    w.line("3. Personal Hygiene", bold=True)
    w.line("Food handlers shall wash hands before work.")


@pytest.fixture
def fssai_pdf(tmp_path: Path) -> Path:
    return build(tmp_path, fssai_page_1, fssai_page_2, fssai_page_3, decorated=True)


@pytest.fixture
def fssai_tree(fssai_pdf: Path) -> Document:
    return parse(fssai_pdf, headings=FSSAI_HEADINGS)


def test_outline_follows_heading_fonts_and_numbering(fssai_tree: Document) -> None:
    assert outline(fssai_tree).splitlines() == [
        "A. OVERVIEW OF MILK INDUSTRY  (p. 1)",
        "  1. Location and Surroundings  (p. 1)",
        "  2. Storage and Material Control  (p. 2)",
        "    2.1 Cold storage  (p. 2)",
        "  3. Personal Hygiene  (p. 3)",
    ]


def test_paragraphs_come_back_whole_in_reading_order_with_pages(fssai_tree: Document) -> None:
    blocks = [(b.type, b.page, b.text) for _, _, b in walk(fssai_tree)][:2]
    assert blocks == [
        (
            BlockType.PROSE,
            1,
            "India has been the leading producer of dairy products since 1998 with "
            "sustained growth in the availability of milk.",
        ),
        (BlockType.PROSE, 1, "Dairy activities form an essential part of the rural economy."),
    ]


def test_list_markers_join_their_text_and_hanging_lines_stay_in_the_item(
    fssai_tree: Document,
) -> None:
    (items,) = [b.items for _, _, b in walk(fssai_tree) if b.type is BlockType.LIST]
    assert items == [
        "i. The facility shall be situated away from polluted areas like open drains.",
        "ii. The site boundaries shall be clearly identified.",
    ]
    # The paragraph after the list (larger gap) is not swallowed by the last item.
    assert "Separate stores shall be provided for chemicals." in texts(fssai_tree, BlockType.PROSE)


def test_running_header_and_page_numbers_are_removed(fssai_tree: Document) -> None:
    all_text = "\n".join(texts(fssai_tree))
    assert "FSMS Guidance Document" not in all_text
    assert all(line.strip() not in {"1", "2", "3"} for line in all_text.splitlines())


def test_table_keeps_header_and_caption_and_its_text_leaves_the_paragraphs(
    fssai_tree: Document,
) -> None:
    (block,) = [b for _, _, b in walk(fssai_tree) if b.table]
    table = block.table
    assert table is not None
    assert table.caption == "Table 2: Storage temperatures"
    assert table.header_rows == [["Product", "Temp °C", "Remarks"]]
    assert table.rows[0] == ["Pasteurised milk", "4 or less", "Chilled"]
    prose = " ".join(texts(fssai_tree, BlockType.PROSE))
    assert "Pasteurised milk" not in prose and "Storage temperatures" not in prose


def test_table_continuing_on_the_next_page_is_joined_without_its_repeated_header(
    fssai_tree: Document,
) -> None:
    (block,) = [b for _, _, b in walk(fssai_tree) if b.table]
    assert block.table is not None
    assert [r[0] for r in block.table.rows] == ["Pasteurised milk", "Ice cream", "Butter"]
    assert (block.page, block.page_end) == (2, 3)


def test_skip_pages_are_left_out(fssai_pdf: Path) -> None:
    tree = parse(fssai_pdf, headings=FSSAI_HEADINGS, skip_pages=["2-3"])
    assert "Storage" not in outline(tree)


def test_table_strategy_none_keeps_table_text_as_lines(fssai_pdf: Path) -> None:
    tree = parse(fssai_pdf, headings=FSSAI_HEADINGS, table_strategy="none")
    assert not [b for _, _, b in walk(tree) if b.table]
    assert any("Pasteurised milk" in t for t in texts(tree))


def test_override_csv_replaces_a_parsed_table(fssai_pdf: Path, tmp_path: Path) -> None:
    from guidance_rag.ingest.overrides import apply_overrides

    tree = parse(fssai_pdf, headings=FSSAI_HEADINGS)
    folder = tmp_path / "overrides" / "doc"
    folder.mkdir(parents=True)
    (folder / "p2-t1.csv").write_text("Product,Temp °C\nMilk,4\n", encoding="utf-8")
    assert apply_overrides(tree, tmp_path / "overrides") == ["p2-t1"]
    (block,) = [b for _, _, b in walk(tree) if b.table]
    assert block.table is not None
    assert block.table.header_rows == [["Product", "Temp °C"]]
    assert block.table.caption == "Table 2: Storage temperatures"  # kept from the parser
    assert block.text.splitlines()[1:] == ["Product | Temp °C", "Milk | 4"]


def test_override_that_matches_no_table_is_an_error(fssai_pdf: Path, tmp_path: Path) -> None:
    from guidance_rag.ingest.overrides import apply_overrides

    tree = parse(fssai_pdf, headings=FSSAI_HEADINGS)
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "p9-t1.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="p9-t1"):
        apply_overrides(tree, tmp_path)


def test_flowchart_pages_keep_only_their_headings(fssai_pdf: Path) -> None:
    tree = parse(fssai_pdf, headings=FSSAI_HEADINGS, headings_only_pages=[1])
    assert not [b for _, _, b in walk(tree) if b.page == 1]
    # The page's top heading still gives later sections their context.
    assert outline(tree).splitlines()[:2] == [
        "A. OVERVIEW OF MILK INDUSTRY  (p. 1)",
        "  2. Storage and Material Control  (p. 2)",
    ]


# --- DGI-like layout: two columns, recommendation boxes, pull quotes ------------------


def dgi_page(page: pymupdf.Page) -> None:
    w = Writer(page, x=50, y=70)
    w.line("GUIDELINE 11", 30, bold=True)
    w.gap(10)
    w.line("Restrict salt intake", 25, bold=True)
    w.gap(8)
    w.line("RATIONALE", 14, bold=True)
    w.line("Increased salt intake may lead to hypertension.", 14, bold=True)
    w.gap(12)
    top = w.y
    left = Writer(page, x=50, y=top)
    left.line("What are the sources of sodium?", 12, bold=True)
    for text in [
        "Habitual diets provide about 300-400mg",
        "of sodium per day. Cereals and pulses",
        "are major sources of sodium. The salt",
        "intake ranges from 3g to 10g per day",
        "in different states of the country and",
        "should be restricted.",
    ]:
        left.line(text, 12)
    right = Writer(page, x=310, y=top)
    for text in [
        "Potassium-rich foods such as fresh",
        "vegetables and fruits decrease blood",
        "pressure. The ratio of sodium to",
        "potassium in the diet is important.",
        "Nuts and flesh foods are also good",
        "sources of potassium.",
    ]:
        right.line(text, 12)
    # A pull quote that the left-column text wraps around, repeating it.
    page.insert_text((190, top + 50), "Salt intake ranges", fontsize=12, fontname=HEAD)
    page.insert_text((190, top + 66), "from 3g to 10g per day", fontsize=12, fontname=HEAD)
    # The box at the end of each guideline is wide and centred, across both columns.
    w.y = max(left.y, right.y) + 20
    w.line("POINTS TO REGISTER", 14, bold=True, x=240)
    w.line("- Use iodized salt in place of common salt in all cooking.", 14, bold=True, x=110)
    w.line("- Restrict the intake of added salt to a maximum of 5g per day.", 14, bold=True, x=110)


@pytest.fixture
def dgi_tree(tmp_path: Path) -> Document:
    path = build(tmp_path, dgi_page)
    return parse(
        path,
        headings=[
            HeadingRule(level=1, min_size=30, bold=True),
            HeadingRule(level=1, min_size=25, bold=True),
            HeadingRule(level=2, min_size=12, bold=True, pattern="^[A-Z]"),
        ],
        recommendation_regex="^(RATIONALE|POINTS TO REGISTER)",
        max_body_font_size=14.5,
        drop_pull_quotes=True,
    )


def test_guideline_number_and_title_lines_make_one_heading(dgi_tree: Document) -> None:
    assert outline(dgi_tree).splitlines() == [
        "GUIDELINE 11 Restrict salt intake  (p. 1)",
        "  What are the sources of sodium?  (p. 1)",
    ]


def test_each_recommendation_box_is_one_block(dgi_tree: Document) -> None:
    recs = texts(dgi_tree, BlockType.RECOMMENDATION)
    assert recs == [
        "RATIONALE Increased salt intake may lead to hypertension.",
        "POINTS TO REGISTER\n- Use iodized salt in place of common salt in all cooking.\n"
        "- Restrict the intake of added salt to a maximum of 5g per day.",
    ]


def test_two_columns_are_read_left_then_right(dgi_tree: Document) -> None:
    assert texts(dgi_tree, BlockType.PROSE) == [
        "Habitual diets provide about 300-400mg of sodium per day. Cereals and pulses are "
        "major sources of sodium. The salt intake ranges from 3g to 10g per day in different "
        "states of the country and should be restricted.",
        "Potassium-rich foods such as fresh vegetables and fruits decrease blood pressure. "
        "The ratio of sodium to potassium in the diet is important. Nuts and flesh foods are "
        "also good sources of potassium.",
    ]


def test_a_sentence_carries_on_from_the_left_column_to_the_right(tmp_path: Path) -> None:
    def page(p: pymupdf.Page) -> None:
        left, right = Writer(p, x=50, y=100), Writer(p, x=310, y=100)
        for text in [
            "Fruits and vegetables are sources of",
            "protective nutrients such as",
            "vitamins, minerals and fibre, and",
            "different varieties of them",
        ]:
            left.line(text, 12)
        for text in [
            "should be consumed every day.",
            "Microgreens are young seedlings",
            "of edible vegetables and herbs.",
            "They are rich in nutrients.",
        ]:
            right.line(text, 12)

    (prose,) = texts(parse(build(tmp_path, page)), BlockType.PROSE)
    assert "different varieties of them should be consumed every day." in prose


def test_pull_quote_is_dropped(dgi_tree: Document) -> None:
    assert "Salt intake ranges" not in "\n".join(texts(dgi_tree))


# --- Bookmarks (JECFA) ------------------------------------------------------------------


def test_bookmarks_give_the_outline_and_wrapped_titles_are_joined(tmp_path: Path) -> None:
    def page(p: pymupdf.Page) -> None:
        w = Writer(p)
        w.line("3. Specific food additives", 14)
        w.line("3.1.4 Carob bean gum and its use in infant formula for special", 10)
        w.line("medical purposes", 10)
        w.line("The Committee established an ADI not specified.")
        w.line("References", 10)
        w.line("1. Smith J. A study of gums. 2020.")

    path = build(tmp_path, page)
    doc = pymupdf.open(path)
    long_title = "3.1.4 Carob bean gum and its use in infant formula for special medical purposes"
    doc.set_toc(
        [[1, "3. Specific food additives", 1], [2, long_title[:70], 1], [2, "References", 1]]
    )
    doc.saveIncr()
    doc.close()

    tree = parse(path, heading_source=HeadingSource.TOC)
    assert outline(tree).splitlines() == [
        "3. Specific food additives  (p. 1)",
        f"  {long_title}  (p. 1)",  # truncated bookmark, full printed title
    ]
    assert texts(tree) == ["The Committee established an ADI not specified."]


# --- OCR -----------------------------------------------------------------------------


def test_scanned_page_is_ocred_and_flagged(tmp_path: Path) -> None:
    def scanned(page: pymupdf.Page) -> None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
        pix.clear_with(255)
        page.insert_image(pymupdf.Rect(50, 100, 500, 700), pixmap=pix)

    seen: list[bytes] = []

    def fake_engine(png: bytes) -> list[OcrBox]:
        seen.append(png)
        return [
            OcrBox("MILK PROCESSING", 300, 300, 700, 330, 0.99),
            OcrBox("Milk is chilled to 4°C or lower.", 300, 400, 1100, 430, 0.98),
            OcrBox("garbage", 300, 500, 400, 530, 0.2),  # low confidence: dropped
        ]

    path = build(tmp_path, scanned)
    tree = parse_pdf(path, doc_id="doc", title="Doc", ocr_engine=fake_engine)
    assert len(seen) == 1 and seen[0].startswith(b"\x89PNG")
    blocks = [b for _, _, b in walk(tree)]
    assert [b.text for b in blocks] == ["MILK PROCESSING", "Milk is chilled to 4°C or lower."]
    assert all(b.ocr and b.page == 1 for b in blocks)


def test_ocr_can_be_switched_off(tmp_path: Path) -> None:
    def scanned(page: pymupdf.Page) -> None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
        page.insert_image(pymupdf.Rect(50, 100, 500, 700), pixmap=pix)

    def engine(png: bytes) -> list[OcrBox]:
        raise AssertionError("OCR should not run")

    path = build(tmp_path, scanned)
    tree = parse_pdf(path, doc_id="d", title="T", config=ParserConfig(ocr=False), ocr_engine=engine)
    assert not list(walk(tree))


# --- Merged cells ---------------------------------------------------------------------


def test_merged_cells_fill_across_or_down_depending_on_the_spanning_cell() -> None:
    # Columns centred at x=25, 75 and 125. Row 2: "Pregnant women" spans columns 0-1.
    raw: list[list[str | None]] = [
        ["Men", "Sedentary", "260"],
        [None, "Moderate", "370"],  # "Men" spans down
        ["Pregnant women", None, "220"],  # spans across
    ]
    boxes: list[list[tuple[float, float, float, float] | None]] = [
        [(0, 0, 50, 10), (50, 0, 100, 10), (100, 0, 150, 10)],
        [None, (50, 10, 100, 20), (100, 10, 150, 20)],
        [(0, 20, 100, 30), None, (100, 20, 150, 30)],
    ]
    assert _expand_merged(raw, boxes) == [
        ["Men", "Sedentary", "260"],
        ["Men", "Moderate", "370"],
        ["Pregnant women", "Pregnant women", "220"],
    ]


def test_sections_carry_their_page(fssai_tree: Document) -> None:
    pages = {s.heading: s.page for _, s in iter_sections(fssai_tree)}
    assert pages["3. Personal Hygiene"] == 3


def test_superscript_zero_before_c_or_f_is_a_degree_sign() -> None:
    # As in FSSAI Poultry: "4" + superscript "0" + "C" must not read as "40C".
    spans = [
        {"text": "chilled at or below 4", "flags": 0},
        {"text": "0", "flags": 1},
        {"text": "C within 4 hours", "flags": 0},
    ]
    assert _span_text(spans) == "chilled at or below 4°C within 4 hours"
    # Other superscripts are kept as they are.
    area = [{"text": "kg/Cm", "flags": 0}, {"text": "2", "flags": 1}, {"text": " (121", "flags": 0}]
    assert _span_text(area) == "kg/Cm2 (121"
