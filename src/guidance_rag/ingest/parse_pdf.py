"""PDF -> document tree (sub-tasks 2.4-2.8).

Pipeline, per document:

1. For each page not in `skip_pages`: find tables (PyMuPDF `find_tables`), then
   extract text lines outside the table areas, with font size, weight and position.
   Pages with no text layer are OCR'd when an OCR engine is available.
2. Remove running headers and footers: lines in the top or bottom margin that
   repeat on many pages, page numbers, and vertical (rotated) text.
3. Join fragments of one visual line ("i." + "The facility shall...") and put the
   page in reading order. Two-column pages are read left column, then right.
4. Classify each line: heading (font rules or the PDF bookmarks), the start of a
   recommendation, a list item, or body text.
5. Assemble paragraphs, lists, recommendations and tables, and build the tree.

Only text, structure and page numbers leave this module. Fonts and coordinates
are used for the decisions above and then dropped.
"""

import logging
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, Protocol

import pymupdf

from guidance_rag.ingest.text import clean_text, join_lines
from guidance_rag.ingest.tree import (
    Block,
    Document,
    Section,
    Table,
    TreeBuilder,
    strip_enumerator,
)
from guidance_rag.models import BlockType, HeadingRule, HeadingSource, ParserConfig, TableStrategy

log = logging.getLogger(__name__)

MARGIN_FRACTION = 0.12  # top/bottom share of the page searched for running headers/footers
RUNNING_MIN_PAGES = 3  # a header must repeat on at least this many pages...
RUNNING_MIN_SHARE = 0.25  # ...and on at least this share of the parsed pages
# A new paragraph starts when the step between lines is larger than the page's usual
# line spacing times PARAGRAPH_STEP (PARAGRAPH_PITCH font sizes if it can't be measured).
PARAGRAPH_PITCH = 1.6
PARAGRAPH_STEP = 1.3
MIN_TEXT_CHARS = 25  # a page with less text than this is treated as scanned (same as check.py)
OCR_DPI = 200
OCR_MIN_SCORE = 0.5

# Bullet glyphs, including symbol-font bullets that extract as "Ÿ", "§", "Ø", "ü" or
# as private-use characters (U+F000-U+F0FF).
_BULLETS = "[•·▪●◦○■□➢➤►✓✔❖\\-–—*ŸØ§ü\\uf000-\\uf0ff]|o(?=\\s)"
# A line made only of a list marker or a section number: "•", "iv.", "a)", "2.1".
_MARKER = (
    rf"(?:{_BULLETS}"
    r"|\(?(?:[ivxl]{1,5}|[IVXL]{1,5}|[a-zA-Z])[.)]|\(?\d{1,2}(?:\.\d{1,2}){0,3}[.)]?)"
)
MARKER_ONLY = re.compile(rf"^{_MARKER}$")
LIST_ITEM = re.compile(rf"^{_MARKER}\s+\S")
_BULLET = re.compile(rf"^(?:{_BULLETS})\s*")
# "Table 1.6. ...", "TABLE A3.1", "Table HACCP Plan: ...", "Table. Suggested ..."
CAPTION = re.compile(r"^(?:Table|TABLE|Tab\.)(?:\s+[\dA-Z]|\s*\d|\.\s)")
_SENTENCE_END = re.compile(r"[.:;?!)\]]$")
_PAGE_NUMBER_KEYS = {"#", "page#", "#page", "-#-", "page#of#", "p#"}
_BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)


# --- Lines and tables with layout -------------------------------------------------


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool
    page: int
    block: int = 0  # PyMuPDF text block on the page (lines of one box share it)
    ocr: bool = False
    column: int = 0  # 0 = spans the page, 1 = left column, 2 = right column
    para_pitch: float = PARAGRAPH_PITCH  # paragraph break threshold, in font sizes
    # Set by classification:
    kind: str = "text"  # text | heading | recommendation | drop
    level: int = 0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def absorb(self, other: "Line") -> None:
        """Append a fragment that sits to the right on the same visual line."""
        self.text = f"{self.text} {other.text}"
        self.x1 = max(self.x1, other.x1)
        self.y0, self.y1 = min(self.y0, other.y0), max(self.y1, other.y1)
        self.size = max(self.size, other.size)
        self.bold = self.bold and other.bold


@dataclass
class PageTable:
    table: Table
    x0: float
    y0: float
    x1: float
    y1: float
    page: int
    column: int = 0


Item = Line | PageTable


@dataclass
class _Page:
    number: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    tables: list[PageTable] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)  # reading order, after step 3


# --- OCR ------------------------------------------------------------------------


@dataclass
class OcrBox:
    text: str
    x0: float  # pixels in the rendered image
    y0: float
    x1: float
    y1: float
    score: float


class OcrEngine(Protocol):
    def __call__(self, png: bytes) -> list[OcrBox]: ...


@cache
def default_ocr_engine() -> OcrEngine | None:
    """RapidOCR with its English model, or None if the `ocr` extra isn't installed."""
    try:
        import onnxruntime
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
    except ImportError:  # the extra, or one of its dependencies (onnxruntime), is missing
        return None
    # onnxruntime's telemetry thread can still be uploading when Python exits, which
    # aborts the process on macOS ("recursive_mutex lock failed", exit code 134).
    onnxruntime.disable_telemetry_events()
    engine = RapidOCR(
        params={
            "Rec.lang_type": LangRec.EN,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
        }
    )

    def run(png: bytes) -> list[OcrBox]:
        result: Any = engine(png)  # RapidOCROutput; the library's return type is a union
        boxes = []
        for quad, text, score in zip(
            result.boxes if result.boxes is not None else [],
            result.txts or [],
            result.scores or [],
            strict=True,
        ):
            xs, ys = [float(p[0]) for p in quad], [float(p[1]) for p in quad]
            boxes.append(OcrBox(str(text), min(xs), min(ys), max(xs), max(ys), float(score)))
        return boxes

    return run


def _ocr_lines(page: pymupdf.Page, number: int, engine: OcrEngine) -> list[Line]:
    png = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
    scale = 72 / OCR_DPI
    lines = []
    for box in engine(png):
        text = clean_text(box.text)
        if box.score < OCR_MIN_SCORE or not text:
            continue
        x0, y0, x1, y1 = (v * scale for v in (box.x0, box.y0, box.x1, box.y1))
        lines.append(Line(text, x0, y0, x1, y1, size=(y1 - y0) * 0.8, bold=False,
                          page=number, ocr=True))  # fmt: skip
    return lines


# --- Step 1: extraction -----------------------------------------------------------


def _is_bold(span: dict[str, object]) -> bool:
    return bool(int(span["flags"]) & 16) or bool(_BOLD_FONT.search(str(span["font"])))  # type: ignore[call-overload]


def _inside(x: float, y: float, boxes: Iterable[tuple[float, float, float, float]]) -> bool:
    return any(x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1 for x0, y0, x1, y1 in boxes)


def _extract_lines(
    page: pymupdf.Page, number: int, exclude: Sequence[tuple[float, float, float, float]]
) -> list[Line]:
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES
    lines = []
    for block_no, block in enumerate(page.get_text("dict", flags=flags)["blocks"]):
        for raw in block.get("lines", []):
            dx, dy = raw["dir"]
            if abs(dy) > 0.1 or dx < 0:  # rotated or vertical text: side labels, watermarks
                continue
            spans = [s for s in raw["spans"] if s["text"].strip()]
            text = _unspace(clean_text(_span_text(raw["spans"])))
            if not spans or not text:
                continue
            x0, y0, x1, y1 = raw["bbox"]
            if _inside((x0 + x1) / 2, (y0 + y1) / 2, exclude):
                continue  # text of a table, which is kept as a table block
            size = round(max(s["size"] for s in spans), 1)
            bold = all(_is_bold(s) for s in spans)
            lines.append(Line(text, x0, y0, x1, y1, size, bold, number, block=block_no))
    return lines


def _span_text(spans: list[dict[str, Any]]) -> str:
    """Join a line's spans, turning a superscript zero before C/F into a degree sign.

    FSSAI PDFs print "4 °C" as "4" + superscript "0" + "C"; read naively that
    becomes "40C", which states the wrong temperature.
    """
    parts = []
    for i, span in enumerate(spans):
        text = span["text"]
        following = spans[i + 1]["text"] if i + 1 < len(spans) else ""
        superscript = bool(span["flags"] & 1)
        if superscript and text.strip() in {"0", "o"} and following[:1] in {"C", "F"}:
            text = "°"
        parts.append(text)
    return "".join(parts)


def _unspace(text: str) -> str:
    """Undo letter-spacing in justified lines: 'U n d e r n o u r i s h e d' -> 'Undernourished'."""
    return re.sub(r"\b(?:\w ){3,}\w\b", lambda m: m.group(0).replace(" ", ""), text)


def _cell(value: str | None) -> str:
    return join_lines(clean_text(value or "").splitlines()) if value else ""


_RAISED_ZERO = re.compile(r"\d ?0 ?[CF]\b")


def _degree_safe_cell(page: pymupdf.Page, value: str | None, box: "Box | None") -> str | None:
    """Re-read a cell from its spans when it may hold a raised-zero degree sign ("40C")."""
    if value is None or box is None or not _RAISED_ZERO.search(value):
        return value
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES
    lines = [
        _span_text(line["spans"])
        for block in page.get_text("dict", clip=box, flags=flags)["blocks"]
        for line in block.get("lines", [])
    ]
    return "\n".join(lines)


def _row_is_bold(page: pymupdf.Page, bbox: tuple[float, float, float, float]) -> bool:
    spans = [
        s
        for b in page.get_text("dict", clip=bbox)["blocks"]
        for line in b.get("lines", [])
        for s in line["spans"]
        if s["text"].strip()
    ]
    return bool(spans) and all(_is_bold(s) for s in spans)


def _extract_tables(page: pymupdf.Page, number: int, strategy: TableStrategy) -> list[PageTable]:
    if strategy is TableStrategy.NONE:
        return []
    found = []
    for i, tab in enumerate(page.find_tables(strategy=strategy.value).tables, start=1):
        if tab.row_count < 2 or tab.col_count < 2:
            continue
        boxes = [row.cells for row in tab.rows]
        raw = [
            [_degree_safe_cell(page, value, box) for value, box in zip(values, row, strict=False)]
            for values, row in zip(tab.extract(), boxes, strict=True)
        ]
        grid = _expand_merged(raw, boxes)
        if tab.header.external:
            header = [[_cell(n) for n in tab.header.names]]
        else:  # leading bold rows are the header (up to 3, for multi-level headers)
            n = 0
            while n < min(3, len(grid) - 1) and _row_is_bold(page, tuple(tab.rows[n].bbox)):
                n += 1
            header, grid = grid[:n], grid[n:]
        table = Table(
            table_id=f"p{number}-t{i}", header_rows=header, rows=[r for r in grid if any(r)]
        )
        table = _drop_empty_columns(table)
        cells = [c for r in table.rows for c in r]
        if table.n_cols >= 2 and cells and sum(1 for c in cells if c) >= 0.3 * len(cells):
            x0, y0, x1, y1 = tab.bbox
            found.append(PageTable(table, x0, y0, x1, y1, page=number))
        # else: a ruled box or figure frame, not a table
    return found


Box = tuple[float, float, float, float]


def _expand_merged(raw: list[list[str | None]], boxes: list[list[Box | None]]) -> list[list[str]]:
    """Fill merged cells so every row stands on its own.

    PyMuPDF returns None for the covered part of a merged cell. If the nearest
    real cell to the left reaches over this column, the cell spans across: copy
    from the left. Otherwise it spans down: copy from the row above.
    """
    n_cols = max(len(r) for r in raw)
    centres: list[float | None] = []
    for j in range(n_cols):
        xs = [(b[0] + b[2]) / 2 for row in boxes if j < len(row) and (b := row[j]) is not None]
        centres.append(sorted(xs)[len(xs) // 2] if xs else None)
    out: list[list[str]] = []
    for r, row in enumerate(raw):
        values: list[str] = []
        for j in range(n_cols):
            value = row[j] if j < len(row) else None
            if value is not None:
                values.append(_cell(value))
                continue
            left = next((k for k in range(j - 1, -1, -1) if boxes[r][k] is not None), None)
            left_box = boxes[r][left] if left is not None else None
            centre = centres[j]
            if left is not None and left_box and centre is not None and left_box[2] > centre:
                values.append(values[left])
            elif out:
                values.append(out[-1][j])
            else:
                values.append("")
        out.append(values)
    return out


def _drop_empty_columns(table: Table) -> Table:
    all_rows = [*table.header_rows, *table.rows]
    keep = [j for j in range(table.n_cols) if any(j < len(r) and r[j] for r in all_rows)]
    return table.model_copy(
        update={
            "header_rows": [[r[j] for j in keep if j < len(r)] for r in table.header_rows],
            "rows": [[r[j] for j in keep if j < len(r)] for r in table.rows],
        }
    )


# --- Step 2: running headers and footers ------------------------------------------


def _running_key(text: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"[\s|]+", "", text.lower()))


def remove_running_lines(pages: list[_Page]) -> None:
    """Drop running headers/footers and page numbers.

    - Lines in the top/bottom margin that repeat on many pages.
    - Page numbers in the margin ("12", "Page 12", "12 | P a g e").
    - Bare numbers elsewhere in the outer quarter of the page that match the
      document's usual offsets between printed and PDF page numbers (landscape
      pages often print the number just under a table, above the margin).
    """

    def in_band(line: Line, page: _Page, share: float) -> bool:
        return line.y1 <= page.height * share or line.y0 >= page.height * (1 - share)

    seen: Counter[str] = Counter()
    offsets: Counter[int] = Counter()
    for page in pages:
        seen.update(
            {_running_key(ln.text) for ln in page.lines if in_band(ln, page, MARGIN_FRACTION)}
        )
        offsets.update(
            int(ln.text) - page.number
            for ln in page.lines
            if ln.text.isdigit() and len(ln.text) <= 3 and in_band(ln, page, MARGIN_FRACTION)
        )
    threshold = max(RUNNING_MIN_PAGES, RUNNING_MIN_SHARE * len(pages))
    repeated = {k for k, n in seen.items() if n >= threshold}
    # Numbering can jump (a missing page), so accept every offset seen on several pages.
    usual_offsets = {k for k, n in offsets.items() if n >= RUNNING_MIN_PAGES}

    def is_running(line: Line, page: _Page) -> bool:
        key = _running_key(line.text)
        if in_band(line, page, MARGIN_FRACTION) and (key in repeated or key in _PAGE_NUMBER_KEYS):
            return True
        return (
            line.text.isdigit()
            and int(line.text) - page.number in usual_offsets
            and in_band(line, page, 0.25)
        )

    for page in pages:
        page.lines = [ln for ln in page.lines if not is_running(ln, page)]


def drop_tiny_fragments(page: _Page) -> None:
    """Drop superscripts and footnote markers left as lines of their own ('2' in kg/m²)."""
    sizes = sorted(ln.size for ln in page.lines)
    if not sizes:
        return
    median = sizes[len(sizes) // 2]
    page.lines = [ln for ln in page.lines if not (len(ln.text) <= 3 and ln.size < 0.7 * median)]


# --- Step 3: visual lines and reading order ---------------------------------------


def _same_row(a: Line, b: Line, share: float = 0.5) -> bool:
    """True if the lines overlap vertically by more than `share` of the shorter one."""
    return min(a.y1, b.y1) - max(a.y0, b.y0) > share * min(a.height, b.height)


def _trigrams(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}


def drop_pull_quotes(page: "_Page") -> None:
    """Remove boxed pull quotes and callouts.

    A text block is a pull quote when body text from another block wraps around
    it on the left (in the same column) for most of its lines, or when its words
    repeat text found elsewhere on the page. Either way it duplicates the body
    text, so dropping it loses nothing and keeps it out of paragraphs and headings.
    """
    _assign_columns(page)
    blocks: dict[int, list[Line]] = {}
    for ln in page.lines:
        blocks.setdefault(ln.block, []).append(ln)
    quotes = set()
    for block, lines in blocks.items():
        wrapped = sum(
            1
            for ln in lines
            if any(
                m.block != block
                and m.column == ln.column
                and m.x1 < ln.x0 - 4
                and m.x1 - m.x0 > 4 * m.size
                and _same_row(m, ln, 0.25)
                for m in page.lines
            )
        )
        own = _trigrams(" ".join(ln.text for ln in lines))
        rest = _trigrams(" ".join(m.text for m in page.lines if m.block != block))
        repeated = len(own) >= 3 and len(own & rest) >= 0.6 * len(own)
        if wrapped >= 0.5 * len(lines) or repeated:
            quotes.add(block)
    page.lines = [ln for ln in page.lines if ln.block not in quotes]


def merge_fragments(lines: list[Line]) -> list[Line]:
    """Join pieces of one visual line: a list marker and its text, or a line
    PyMuPDF split in two. Lines in different columns stay apart."""
    rows: list[Line] = []
    for ln in sorted(lines, key=lambda line: line.x0):
        for row in rows:
            gap = ln.x0 - row.x1
            limit = 80.0 if MARKER_ONLY.match(row.text) else 0.8 * max(row.size, ln.size)
            if _same_row(row, ln) and -1 <= gap <= limit:
                row.absorb(ln)
                break
        else:
            rows.append(ln)
    return rows


def _assign_columns(page: _Page) -> bool:
    """Mark each line/table left, right or full width. True if the page has two columns."""
    mid = page.width / 2
    items: list[Item] = [*page.lines, *page.tables]
    for it in items:
        it.column = 1 if it.x1 <= mid + 8 else 2 if it.x0 >= mid - 8 else 0
    right_starts = Counter(round(it.x0) for it in page.lines if it.column == 2)
    left = sum(1 for it in page.lines if it.column == 1)
    two_columns = left >= 3 and sum(n for x, n in right_starts.items() if n >= 3) >= 3
    if not two_columns:
        for it in items:
            it.column = 0
    return two_columns


def set_paragraph_pitch(items: list[Item]) -> None:
    """Measure the page's usual line spacing (in font sizes) and set each line's
    paragraph-break threshold from it. Double-spaced pages get a higher threshold."""
    lines = [it for it in items if isinstance(it, Line)]
    ratios = sorted(
        (b.y0 - a.y0) / a.size
        for a, b in pairwise(lines)
        if a.column == b.column and abs(a.size - b.size) < 0.5 and 0 < b.y0 - a.y0 < 2.5 * a.size
    )
    if len(ratios) < 5:
        return
    pitch = max(PARAGRAPH_STEP * ratios[len(ratios) // 2], 1.15)
    for ln in lines:
        ln.para_pitch = pitch


def order_items(page: _Page) -> list[Item]:
    """Reading order: top to bottom; on two-column pages, each band between
    full-width items is read left column first, then right column."""
    two_columns = _assign_columns(page)
    items: list[Item] = sorted([*page.lines, *page.tables], key=lambda it: (round(it.y0), it.x0))
    if not two_columns:
        return items
    ordered: list[Item] = []
    band: list[Item] = []
    for it in items:
        if it.column == 0:
            ordered += [b for b in band if b.column == 1] + [b for b in band if b.column == 2]
            band = []
            ordered.append(it)
        else:
            band.append(it)
    ordered += [b for b in band if b.column == 1] + [b for b in band if b.column == 2]
    return ordered


# --- Step 4: classification -------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def heading_level(line: Line, rules: Sequence[HeadingRule], config: ParserConfig) -> int | None:
    text = line.text
    if len(text) > config.heading_max_chars or not re.search(r"[A-Za-z]", text):
        return None
    if config.heading_exclude_regex and re.search(config.heading_exclude_regex, text):
        return None
    for rule in rules:
        low, high = rule.size_range
        if not low <= line.size <= high:
            continue
        if rule.bold is not None and rule.bold != line.bold:
            continue
        if rule.pattern and not re.search(rule.pattern, text):
            continue
        level = rule.level
        if rule.nest_by_number and (m := re.match(r"(\d+(?:\.\d+)*)", text)):
            level += m.group(1).count(".")
        return min(level, 6)
    return None


def apply_toc(pages: list[_Page], toc: list[tuple[int, str, int]]) -> int:
    """Mark the lines that start each bookmark's heading. Returns how many bookmarks
    could not be matched to a line; those headings are put at the top of their page."""
    by_page: dict[int, list[tuple[int, str]]] = {}
    for level, title, page_no in toc:
        title = clean_text(title)
        if title and page_no > 0:
            by_page.setdefault(page_no, []).append((level, title))
    unmatched = 0
    for page in pages:
        start = 0
        items = page.items
        for level, title in by_page.get(page.number, []):
            target = _norm(title)
            for i in range(start, len(items)):
                it = items[i]
                if not isinstance(it, Line) or it.kind != "text":
                    continue
                key = _norm(it.text)
                starts = target.startswith(key) and len(key) >= min(len(target), 4)
                runs_past = len(target) >= 40 and key.startswith(target)  # truncated bookmark
                if key and (starts or runs_past):
                    # Take following lines while they continue the title. Bookmark titles
                    # can be truncated, so a line may also run past the end of the title.
                    parts, combined, j = [it.text], key, i + 1
                    while len(combined) < len(target) and j < len(items):
                        nxt = items[j]
                        if not isinstance(nxt, Line) or not (nkey := _norm(nxt.text)):
                            break
                        joined = combined + nkey
                        if not (target.startswith(joined) or joined.startswith(target)):
                            break
                        parts.append(nxt.text)
                        combined = joined
                        nxt.kind = "drop"
                        j += 1
                    it.kind, it.level = "heading", level
                    it.text = join_lines(parts) if len(combined) >= len(target) else title
                    start = j
                    break
            else:
                unmatched += 1
                first = next((it for it in items if isinstance(it, Line)), None)
                y = first.y0 - 1 if first else 0.0
                items.insert(
                    start,
                    Line(title, 0, y, 0, y, 0, True, page.number, kind="heading", level=level),
                )
                start += 1
    return unmatched


def classify(pages: list[_Page], config: ParserConfig) -> None:
    recommendation = (
        re.compile(config.recommendation_regex) if config.recommendation_regex else None
    )
    headings_only = config.headings_only_page_set
    for page in pages:
        for it in page.items:
            if not isinstance(it, Line) or it.kind != "text":
                continue
            if config.heading_source is HeadingSource.FONTS:
                level = heading_level(it, config.headings, config)
                if level is not None:
                    it.kind, it.level = "heading", level
                    continue
            if page.number in headings_only:
                it.kind = "drop"
                continue
            if recommendation and recommendation.search(it.text):
                it.kind = "recommendation"
            elif config.max_body_font_size and it.size > config.max_body_font_size:
                it.kind = "drop"
        _demote_run_in_headings(page.items)


def _demote_run_in_headings(items: list[Item]) -> None:
    """A bold lead-in whose sentence carries on in the next line ('...for infants and'
    / 'children in India: A child is...') is body text, not a heading."""
    for it, nxt in pairwise(items):
        if (
            isinstance(it, Line)
            and isinstance(nxt, Line)
            and it.kind == "heading"
            and nxt.kind == "text"
            and nxt.text[:1].islower()
            and not LIST_ITEM.match(nxt.text)  # "i. The facility shall..." is a list item
            and nxt.column == it.column
            and 0 <= nxt.y0 - it.y1 < 0.6 * it.size
        ):
            it.kind = "text"


# --- Step 5: blocks and tree ------------------------------------------------------


def _ends_sentence(text: str) -> bool:
    return bool(_SENTENCE_END.search(text))


def starts_new_paragraph(prev: Line, line: Line) -> bool:
    if CAPTION.match(line.text) or abs(line.size - prev.size) > 1 or line.bold != prev.bold:
        return True
    if prev.page != line.page or prev.column != line.column:
        return _ends_sentence(prev.text)  # carry on across a page or column break mid-sentence
    if line.y0 < prev.y0:
        return True  # moved up: a new column band or a side box
    if line.y0 - prev.y0 > line.para_pitch * max(prev.size, line.size):
        return True
    indented = line.x0 > prev.x0 + 0.8 * line.size
    return indented and _ends_sentence(prev.text)


def _item_text(line: Line) -> str:
    """List item text: bullets are dropped, enumerators such as 'iv.' or '2)' are kept."""
    return _BULLET.sub("", line.text, count=1)


class _Assembler:
    """Turns classified items into headings and blocks on a TreeBuilder."""

    def __init__(self, builder: TreeBuilder) -> None:
        self.b = builder
        self.para: list[Line] = []
        self.items: list[list[Line]] = []  # open list: one list of lines per item
        self.rec: list[Line] = []  # open recommendation
        self.last_heading: Line | None = None
        self.last_section: Section | None = None  # opened by last_heading, if any
        self.last_table: Block | None = None
        self.last_item_kind = ""

    # -- emitting --

    @staticmethod
    def _pages(lines: list[Line]) -> dict[str, int | None]:
        first, last = lines[0].page, lines[-1].page
        return {"page": first, "page_end": last if last != first else None}

    def flush(self) -> None:
        if self.para:
            text = join_lines([ln.text for ln in self.para])
            self.emit(Block(type=BlockType.PROSE, text=text, **self._pages(self.para),
                            ocr=any(ln.ocr for ln in self.para)))  # fmt: skip
        if self.items:
            texts = [join_lines([_item_text(lines[0]), *(ln.text for ln in lines[1:])])
                     for lines in self.items]  # fmt: skip
            flat = [ln for lines in self.items for ln in lines]
            self.emit(Block.from_items(texts, **self._pages(flat), ocr=any(ln.ocr for ln in flat)))
        if self.rec:
            parts: list[list[str]] = []
            for ln in self.rec:
                if not parts or LIST_ITEM.match(ln.text) or ln.kind == "recommendation":
                    parts.append([])
                parts[-1].append(ln.text)
            text = "\n".join(join_lines(p) for p in parts)
            self.emit(Block(type=BlockType.RECOMMENDATION, text=text, **self._pages(self.rec),
                            ocr=any(ln.ocr for ln in self.rec)))  # fmt: skip
        self.para, self.items, self.rec = [], [], []

    def emit(self, block: Block) -> None:
        self.b.block(block)
        self.last_table = None

    # -- consuming --

    def heading(self, line: Line) -> None:
        self.flush()
        prev = self.last_heading
        if (
            prev is not None
            and self.last_item_kind == "heading"
            and (prev.level == line.level or abs(prev.size - line.size) < 0.5)
            and strip_enumerator(line.text) == line.text  # "2.1 ..." is a heading of its own
            and prev.bold == line.bold
            and prev.page == line.page
            and line.y0 - prev.y1 < 2.5 * max(prev.size, line.size)
        ):
            # Second line of a wrapped heading: extend the section it opened.
            if self.last_section is not None:
                self.last_section.heading = join_lines([self.last_section.heading, line.text])
            prev.y1 = line.y1
            return
        self.last_section = self.b.heading(line.text, line.level, page=line.page)
        self.last_heading = line

    def table(self, pt: PageTable, first_on_page: bool) -> None:
        self.flush()
        prev = self.last_table
        table = pt.table
        if first_on_page and prev is not None and prev.table and prev.table.n_cols == table.n_cols:
            # The table continues from the previous page; drop a repeated header row.
            rows = table.rows
            if (
                rows
                and prev.table.header_rows
                and _norm(" ".join(rows[0])) == _norm(" ".join(prev.table.header_rows[0]))
            ):
                rows = rows[1:]
            if table.header_rows and table.header_rows != prev.table.header_rows:
                rows = [*table.header_rows, *rows]
            prev.table.rows.extend(rows)
            prev.text = prev.table.to_text()
            prev.page_end = pt.page
            return
        caption = self._take_caption()
        if caption:
            table = table.model_copy(update={"caption": caption})
        block = Block.from_table(table, page=pt.page)
        self.b.block(block)
        self.last_table = block

    def _take_caption(self) -> str | None:
        """Move a 'Table N ...' paragraph just above the table into its caption, with a
        short note that sits between them ('(Quantities are for the given body weights.)')."""
        section = self.b.current
        if not section:
            return None
        blocks = section.blocks
        for n in (1, 2):
            if len(blocks) < n:
                break
            candidates = blocks[-n:]
            first, notes = candidates[0], candidates[1:]
            if (
                all(b.type is BlockType.PROSE for b in candidates)
                and CAPTION.match(first.text)
                and len(first.text) < 250
                and all(len(b.text) < 300 for b in notes)
            ):
                del blocks[-n:]
                return " ".join(b.text for b in candidates)
        return None

    def line(self, line: Line) -> None:
        if line.kind == "recommendation":
            self.flush()
            self.rec = [line]
            return
        if self.rec:
            self.rec.append(line)
            return
        if LIST_ITEM.match(line.text) and not CAPTION.match(line.text):
            if self.para:
                self.flush()
            self.items.append([line])
            return
        if self.items:
            last, first = self.items[-1][-1], self.items[-1][0]
            same_flow = last.page == line.page and last.column == line.column
            # Continuation lines may be indented under the item text or hang back
            # under the marker; either way they follow at normal line spacing.
            if (
                same_flow
                and line.x0 >= first.x0 - 2
                and 0 <= line.y0 - last.y0 <= line.para_pitch * line.size
            ) or (not same_flow and not _ends_sentence(last.text)):
                self.items[-1].append(line)
                return
            self.flush()
        if self.para and starts_new_paragraph(self.para[-1], line):
            self.flush()
        self.para.append(line)

    def feed(self, pages: list[_Page]) -> None:
        for page in pages:
            first = True
            for it in page.items:
                if isinstance(it, PageTable):
                    self.table(it, first)
                    self.last_item_kind = "table"
                elif it.kind == "heading":
                    self.heading(it)
                    self.last_item_kind = "heading"
                elif it.kind != "drop":
                    self.line(it)
                    self.last_item_kind = "line"
                    self.last_table = None
                else:
                    continue
                first = False
        self.flush()


# --- Entry point ------------------------------------------------------------------


def parse_pdf(
    path: Path,
    *,
    doc_id: str,
    title: str,
    config: ParserConfig | None = None,
    ocr_engine: OcrEngine | Literal["auto"] | None = "auto",
) -> Document:
    """Parse a PDF into a document tree.

    `ocr_engine` is an engine, None (no OCR), or "auto": load RapidOCR the first
    time a page needs it, if the `ocr` extra is installed.
    """
    config = config or ParserConfig()
    skip = config.skip_page_set
    pages: list[_Page] = []
    with pymupdf.open(path) as pdf:
        toc = pdf.get_toc(simple=True) if config.heading_source is HeadingSource.TOC else []
        for index in range(pdf.page_count):
            number = index + 1
            if number in skip:
                continue
            page = pdf[index]
            parsed = _Page(number, page.rect.width, page.rect.height)
            parsed.tables = _extract_tables(page, number, config.table_strategy)
            boxes = [(t.x0, t.y0, t.x1, t.y1) for t in parsed.tables]
            parsed.lines = _extract_lines(page, number, boxes)
            no_text = sum(len(ln.text) for ln in parsed.lines) < MIN_TEXT_CHARS
            if no_text and not parsed.tables and config.ocr and page.get_images():
                engine = default_ocr_engine() if ocr_engine == "auto" else ocr_engine
                if engine is None:
                    log.warning("%s p.%d has no text layer and no OCR engine is installed "
                                "(uv sync --extra ocr)", doc_id, number)  # fmt: skip
                else:
                    parsed.lines = _ocr_lines(page, number, engine)
            pages.append(parsed)

    remove_running_lines(pages)
    for p in pages:
        drop_tiny_fragments(p)
        if config.drop_pull_quotes:
            drop_pull_quotes(p)
        p.lines = merge_fragments(p.lines)
        if any(ln.ocr for ln in p.lines):
            # Scanned checklists: item numbers have merged with their text by now;
            # numbers left on their own are score columns.
            p.lines = [ln for ln in p.lines if not re.fullmatch(r"[\d*]{1,3}", ln.text)]
        p.items = order_items(p)
        set_paragraph_pitch(p.items)
    if toc:
        unmatched = apply_toc(pages, toc)
        if unmatched:
            log.info("%s: %d bookmark(s) not found on their page", doc_id, unmatched)
    classify(pages, config)

    builder = TreeBuilder(doc_id, config.drop_sections)
    _Assembler(builder).feed(pages)
    return builder.build(title)
