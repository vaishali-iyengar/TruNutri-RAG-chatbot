"""Document tree: the parsers' output and the chunker's input (ARCHITECTURE.md §5.1).

A `Document` is a list of top-level `Section`s. Each section has a heading, the
blocks that sit directly under it, and its subsections. Blocks are typed
(prose, list, table, recommendation) so the chunker can keep tables and
recommendations whole.

The tree holds only what later stages need: text, structure, page numbers and
anchors for deep links. Layout detail (fonts, coordinates) stays in the parsers.
"""

import re
from collections.abc import Iterator
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guidance_rag.models import BlockType


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Table(_Model):
    """A table with its header row(s) kept apart from the body rows.

    Merged cells are expanded, so every row has one value per column and can be
    read on its own (e.g. each storage-chart row repeats its food category).
    """

    table_id: str | None = None  # e.g. "p28-t1"; names the override CSV in corpus/overrides/
    caption: str | None = None
    header_rows: list[list[str]] = Field(default_factory=list)
    rows: list[list[str]]

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in [*self.header_rows, *self.rows]), default=0)

    def to_text(self) -> str:
        """Plain-text rendering: one line per row, cells separated by ' | '."""
        lines = [self.caption] if self.caption else []
        lines += [" | ".join(r) for r in [*self.header_rows, *self.rows]]
        return "\n".join(lines)


class Block(_Model):
    """One unit of content under a section heading."""

    type: BlockType
    text: str  # plain text; for tables, see Table.to_text()
    page: int | None = None  # 1-based page where the block starts (PDF only)
    page_end: int | None = None  # set when the block runs onto later pages
    table: Table | None = None  # set for TABLE blocks only
    items: list[str] = Field(default_factory=list)  # set for LIST blocks only
    ocr: bool = False  # text came from OCR of a scanned page

    @model_validator(mode="after")
    def _check_type_fields(self) -> Self:
        if (self.type is BlockType.TABLE) != (self.table is not None):
            raise ValueError("a table is required for TABLE blocks and only for them")
        if self.items and self.type is not BlockType.LIST:
            raise ValueError("items are only allowed on LIST blocks")
        return self

    @classmethod
    def from_table(cls, table: Table, **kwargs: object) -> Self:
        return cls(type=BlockType.TABLE, text=table.to_text(), table=table, **kwargs)

    @classmethod
    def from_items(cls, items: list[str], **kwargs: object) -> Self:
        return cls(type=BlockType.LIST, text="\n".join(items), items=items, **kwargs)


class Section(_Model):
    heading: str
    level: int = Field(ge=1)  # 1 = top level; children have higher levels
    page: int | None = None  # page of the heading (PDF only)
    anchor: str | None = None  # HTML fragment for deep links, without '#'
    blocks: list[Block] = Field(default_factory=list)
    children: list["Section"] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.blocks and all(c.is_empty() for c in self.children)


class Document(_Model):
    doc_id: str
    sections: list[Section] = Field(default_factory=list)


# --- Building a tree ----------------------------------------------------------

# Sections that add noise and no guidance (ARCHITECTURE.md §5.2: front matter,
# contents, references). Matched case-insensitively against the heading with its
# leading number removed.
DEFAULT_DROP_SECTIONS = [
    r"^references?\b",
    r"^bibliography\b",
    r"^(table of )?contents$",
    r"^glossary$",
    r"^(list of )?(acronyms|abbreviations)\b",
    r"^acknowledge?ments?$",
]

# A leading enumerator: "A.", "II.", "2.1", "3.1.4", "1)" ...
_ENUMERATOR = re.compile(r"^\s*(?:[A-Z]|[IVXL]+|\d+(?:\.\d+)*)\s*[.):]?\s+(?=\S)")


def strip_enumerator(heading: str) -> str:
    return _ENUMERATOR.sub("", heading, count=1)


def _heading_key(heading: str) -> str:
    """Normalised heading for spotting repeats ('A. OVERVIEW OF X' == 'Overview of X:')."""
    return re.sub(r"[^a-z0-9]+", " ", strip_enumerator(heading).lower()).strip()


class TreeBuilder:
    """Builds a Document from a flat stream of headings and blocks in reading order.

    - A heading closes every open section at its level or deeper.
    - A heading that repeats the open, still-empty section at the same level is
      merged into it (FSSAI divider pages repeat the next page's title).
    - Sections whose heading matches a drop pattern are discarded with their content.
    - Sections left with no content are pruned by `build()`.
    """

    def __init__(self, doc_id: str, drop_sections: list[str] | None = None) -> None:
        self._doc_id = doc_id
        self._drop = [re.compile(p, re.IGNORECASE) for p in DEFAULT_DROP_SECTIONS]
        self._drop += [re.compile(p, re.IGNORECASE) for p in drop_sections or []]
        self._roots: list[Section] = []
        self._stack: list[Section] = []
        self._dropping_level: int | None = None  # inside a dropped section at this level
        self._preamble: list[Block] = []  # blocks before the first heading

    def heading(
        self, text: str, level: int, *, page: int | None = None, anchor: str | None = None
    ) -> Section | None:
        """Open a section. Returns it, or None if the heading was merged or dropped."""
        text = " ".join(text.split())
        if not text:
            return None
        if self._dropping_level is not None:
            if level > self._dropping_level:
                return None
            self._dropping_level = None
        while self._stack and self._stack[-1].level > level:
            self._stack.pop()
        top = self._stack[-1] if self._stack else None
        if (
            top
            and top.level == level
            and top.is_empty()
            and _heading_key(top.heading) == _heading_key(text)
        ):
            return None  # repeated title; keep the first (it usually carries the enumerator)
        if top and top.level == level:
            self._stack.pop()
        if any(p.search(strip_enumerator(text)) for p in self._drop):
            self._dropping_level = level
            return None
        section = Section(heading=text, level=level, page=page, anchor=anchor)
        (self._stack[-1].children if self._stack else self._roots).append(section)
        self._stack.append(section)
        return section

    def block(self, block: Block) -> None:
        if self._dropping_level is not None:
            return
        if self._stack:
            self._stack[-1].blocks.append(block)
        else:
            self._preamble.append(block)

    @property
    def current(self) -> Section | None:
        return self._stack[-1] if self._stack and self._dropping_level is None else None

    def build(self, title: str) -> Document:
        """Return the tree. Blocks before the first heading go under a `title` section."""
        roots = self._roots
        if self._preamble:
            roots = [Section(heading=title, level=1, blocks=self._preamble), *roots]
        return Document(doc_id=self._doc_id, sections=_prune(roots))


def _prune(sections: list[Section]) -> list[Section]:
    kept = []
    for s in sections:
        s.children = _prune(s.children)
        if not s.is_empty():
            kept.append(s)
    return kept


# --- Reading a tree -------------------------------------------------------------


def iter_sections(doc: Document) -> Iterator[tuple[list[str], Section]]:
    """Yield every section depth-first, with its heading path."""

    def visit(section: Section, path: list[str]) -> Iterator[tuple[list[str], Section]]:
        here = [*path, section.heading]
        yield here, section
        for child in section.children:
            yield from visit(child, here)

    for top in doc.sections:
        yield from visit(top, [])


def walk(doc: Document) -> Iterator[tuple[list[str], Section, Block]]:
    """Yield every block in reading order with its section path and section.

    The path lists headings from the top level down, e.g.
    ["GUIDELINE 11 Restrict salt intake", "How to avoid excess salt intake?"].
    """
    for path, section in iter_sections(doc):
        for block in section.blocks:
            yield path, section, block


def outline(doc: Document, *, counts: bool = False) -> str:
    """The heading tree as indented text, optionally with block counts per section."""
    lines = []
    for path, section in iter_sections(doc):
        indent = "  " * (len(path) - 1)
        page = f"  (p. {section.page})" if section.page else ""
        line = f"{indent}{section.heading}{page}"
        if counts and section.blocks:
            tally: dict[str, int] = {}
            for b in section.blocks:
                tally[b.type.value] = tally.get(b.type.value, 0) + 1
            line += "  [" + ", ".join(f"{k} {v}" for k, v in tally.items()) + "]"
        lines.append(line)
    return "\n".join(lines)
