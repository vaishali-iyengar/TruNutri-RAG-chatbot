"""HTML page -> document tree (sub-task 2.3).

Keeps only the page's main content: h1-h6 become nested sections, p paragraphs,
ul/ol list blocks and table table blocks. Navigation, footers, buttons, share
links and cookie banners are removed first.

Tables have merged cells expanded (rowspan/colspan), so in the FoodSafety.gov
chart every row carries its food category ("Hot dogs | Opened package | 1 week").
"""

from urllib.parse import quote

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag

from guidance_rag.ingest.text import clean_text
from guidance_rag.ingest.tree import Block, Document, Table, TreeBuilder
from guidance_rag.models import BlockType, ParserConfig

# Removed wherever they appear in the content.
NOISE_SELECTORS = [
    "script", "style", "noscript", "template", "iframe", "svg", "img", "picture", "video",
    "nav", "header", "footer", "aside", "form", "button",
    "[role=navigation]", "[role=banner]", "[role=contentinfo]", "[aria-hidden=true]",
    "[class*=breadcrumb]", "[class*=cookie]", "[id*=cookie]", "[class*=related]",
    "[class*=share]", "[class*=social]", ".usa-button",
]  # fmt: skip

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
LIST_TAGS = {"ul", "ol"}
# Elements that start a new line of text (used when flattening a cell or list item).
_BLOCKISH = {"p", "div", "li", "br", "tr", "td", "th", "dd", "dt", *HEADING_TAGS, *LIST_TAGS}
# Inline elements whose text belongs to the surrounding paragraph.
_INLINE = {
    "a",
    "abbr",
    "b",
    "cite",
    "code",
    "em",
    "i",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "u",
}


def text_fragment(text: str) -> str:
    """A text-fragment directive that scrolls a browser to `text` (no '#')."""
    return ":~:text=" + quote(text, safe="")


def _text(el: Tag) -> str:
    parts: list[str] = []
    for node in el.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif isinstance(node, Tag) and node.name in _BLOCKISH:
            parts.append(" ")
    return clean_text("".join(parts))


def _list_items(el: Tag) -> list[str]:
    """One string per item. Nested lists are folded into their parent item as '  - sub'."""
    items = []
    for n, li in enumerate(el.find_all("li", recursive=False), start=1):
        nested = [c for c in li.find_all(LIST_TAGS) if c.find_parent("li") is li]
        for sub in nested:
            sub.extract()
        text = _text(li)
        if el.name == "ol" and text:
            text = f"{n}. {text}"
        sub_items = [f"  - {s}" for sub in nested for s in _list_items(sub)]
        if text or sub_items:
            items.append("\n".join([text, *sub_items]) if text else "\n".join(sub_items))
    return items


def _span(cell: Tag, attr: str) -> int:
    try:
        return max(1, min(int(str(cell.get(attr) or 1)), 100))
    except ValueError:
        return 1


def _fill_carried(row: list[str], carried: dict[int, tuple[str, int]]) -> None:
    """Copy cells from rows above that span down into the next columns of `row`."""
    while len(row) in carried:
        text, left = carried.pop(len(row))
        if left > 1:
            carried[len(row)] = (text, left - 1)
        row.append(text)


def _table(el: Tag) -> Table | None:
    """Expand the table into a full grid, so each row stands on its own."""
    grid: list[list[str]] = []
    is_header: list[bool] = []
    carried: dict[int, tuple[str, int]] = {}  # column -> (text, rows still to fill)
    for tr in el.find_all("tr"):
        if tr.find_parent("table") is not el:
            continue  # row of a nested table
        cells = tr.find_all(["td", "th"], recursive=False)
        row: list[str] = []
        for cell in cells:
            _fill_carried(row, carried)
            text, rowspan, colspan = _text(cell), _span(cell, "rowspan"), _span(cell, "colspan")
            for _ in range(colspan):
                if rowspan > 1:
                    carried[len(row)] = (text, rowspan - 1)
                row.append(text)
        _fill_carried(row, carried)
        while carried and max(carried) > len(row):  # a gap before a spanning cell
            row.append("")
            _fill_carried(row, carried)
        if any(row):
            grid.append(row)
            in_thead = tr.find_parent("thead") is not None
            is_header.append(in_thead or all(c.name == "th" for c in cells))
    if not grid:
        return None
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    n_header = 0
    while n_header < len(grid) - 1 and is_header[n_header]:
        n_header += 1
    caption = el.find("caption")
    return Table(
        table_id=str(el.get("id")) if el.get("id") else None,
        caption=_text(caption) if caption else None,
        header_rows=grid[:n_header],
        rows=grid[n_header:],
    )


class _HtmlWalker:
    def __init__(self, builder: TreeBuilder) -> None:
        self.b = builder
        self.inline: list[str] = []  # loose text waiting to become a paragraph

    def flush(self) -> None:
        text = clean_text(" ".join(self.inline))
        self.inline = []
        if text:
            self.b.block(Block(type=BlockType.PROSE, text=text))

    def heading(self, el: Tag) -> None:
        text = _text(el)
        if text:
            anchor = str(el["id"]) if el.get("id") else text_fragment(text)
            self.b.heading(text, int(el.name[1]), anchor=anchor)

    def visit(self, el: Tag) -> None:
        for child in el.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                self.inline.append(str(child))
            elif not isinstance(child, Tag):
                continue
            elif child.name in _INLINE:
                self.inline.append(_text(child))
            elif child.name in HEADING_TAGS:
                self.flush()
                self.heading(child)
            elif child.name == "p":
                self.flush()
                self.inline.append(_text(child))
                self.flush()
            elif child.name in LIST_TAGS:
                self.flush()
                items = _list_items(child)
                if items:
                    self.b.block(Block.from_items(items))
            elif child.name == "table":
                self.flush()
                table = _table(child)
                if table:
                    self.b.block(Block.from_table(table))
            else:  # div, section, article, ...
                self.flush()
                self.visit(child)
        self.flush()


def parse_html(
    html: str, *, doc_id: str, title: str, config: ParserConfig | None = None
) -> Document:
    config = config or ParserConfig()
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    root = soup.select_one(config.content_selector) if config.content_selector else None
    root = root or soup.find("main") or soup.find("article") or soup.body or soup
    for selector in [*NOISE_SELECTORS, *config.drop_selectors]:
        for el in root.select(selector):
            el.decompose()

    builder = TreeBuilder(doc_id, config.drop_sections)
    walker = _HtmlWalker(builder)
    # The page title often sits outside the main content element; it becomes the top section.
    if isinstance(h1, Tag) and all(parent is not root for parent in h1.parents):
        walker.heading(h1)
    walker.visit(root)
    return builder.build(title)
