"""Structure-aware chunking (implementation-plan.md, Phase 3; ARCHITECTURE.md §5.2).

Chunk boundaries come from the document tree, not from a token count:

- A chunk never crosses into another section. The one exception is a run of
  small sibling sections, which are merged under their parent (3.3).
- Within a section, paragraphs and short lists are packed in order up to
  `prose_max` tokens, cutting only between blocks, with a one-paragraph overlap
  when the section needs several chunks (3.2).
- Each recommendation is one chunk (3.4).
- A table is one chunk when small; a large one is split between rows, never
  inside a first-column category, with its title and header repeated (3.5-3.6).
- A long list is split between items, with its lead-in sentence repeated (3.7).

Every chunk carries the document's provenance, its section path, pages and a
deep link, plus `embed_text`: the body behind a contextual header (3.8).
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import tiktoken

from guidance_rag.config import PROJECT_ROOT, ChunkingConfig
from guidance_rag.ingest.fetch import DEFAULT_RAW_DIR
from guidance_rag.ingest.parse import DEFAULT_PARSED_DIR, load_or_parse
from guidance_rag.ingest.tree import Block, Document, Section, Table
from guidance_rag.models import BlockType, Chunk, DocumentFormat, SourceDocument

# A list item that already carries its own number or letter ("iv. ...", "2) ...").
_ENUMERATED = re.compile(r"^\(?(?:\d{1,2}(?:\.\d{1,2})*|[ivxlIVXL]{1,5}|[a-zA-Z])[.)]\s")
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'“])")


@cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Token count with a fixed tokenizer (cl100k_base), used as a stable approximation."""
    return len(_encoding().encode(text, disallowed_special=()))


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "section"


# --- Report ------------------------------------------------------------------------


@dataclass
class ChunkReport:
    """What the chunker noticed while chunking one document (shown in the QC report)."""

    doc_id: str
    split_tables: dict[str, int] = field(default_factory=dict)  # table_id -> number of chunks
    flagged_tables: dict[str, list[str]] = field(default_factory=dict)  # table_id -> reasons
    headerless_tables: list[str] = field(default_factory=list)
    split_categories: list[str] = field(default_factory=list)  # "table_id: category"
    split_items: int = 0  # list items too long for one chunk, split at sentences
    split_recommendations: int = 0


# --- Pieces of a chunk before metadata is attached ----------------------------------


@dataclass
class _Piece:
    """A chunk body plus where it came from."""

    text: str
    block_type: BlockType
    blocks: list[Block]
    path: list[str]
    section: Section
    subsections: list[str] = field(default_factory=list)
    table_id: str | None = None


# --- Text of blocks -----------------------------------------------------------------


def list_item_line(item: str) -> str:
    """A list item as text: enumerated items keep their number, others get a dash."""
    return item if _ENUMERATED.match(item) else f"- {item}"


def block_text(block: Block) -> str:
    if block.type is BlockType.LIST and block.items:
        return "\n".join(list_item_line(i) for i in block.items)
    return block.text


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text) if s.strip()]


# --- Tables -------------------------------------------------------------------------


MERGED_CELL_MIN_CHARS = 30


def dedupe_row(row: list[str], header: bool = False) -> list[str]:
    """Blank a value repeated from the cell to its left: one merged cell spanning columns.

    Header rows lose every repeat ("Men | Men | Women" -> "Men |  | Women"). In body
    rows short equal values are usually real ("4 to 8 °C" for two products), so only
    long repeated text, which is what a merged text box looks like, is blanked.
    """
    return [
        "" if i > 0 and c == row[i - 1] and (header or len(c) > MERGED_CELL_MIN_CHARS) else c
        for i, c in enumerate(row)
    ]


def _md_cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ").strip()


def column_names(table: Table) -> list[str]:
    """One name per column, joining multi-row headers ("Corrective Action / Immediate")."""
    names = []
    for j in range(table.n_cols):
        parts: list[str] = []
        for row in table.header_rows:
            value = row[j] if j < len(row) else ""
            if value and value not in parts:
                parts.append(value)
        names.append(" / ".join(parts) or f"Column {j + 1}")
    return names


class TableWriter:
    """Serialises a table: Markdown when narrow, one "column: value" line per row when wide."""

    def __init__(self, table: Table, title: str, config: ChunkingConfig) -> None:
        self.table = table
        self.title = title
        self.wide = table.n_cols > config.wide_table_columns
        self.names = column_names(table)

    def head(self) -> str:
        """Title and header: repeated at the top of every piece of the table."""
        lines = [self.title]
        if self.wide:
            if self.table.header_rows:
                lines.append("Columns: " + " | ".join(self.names))
        else:
            for row in self.table.header_rows:
                cells = dedupe_row(row, header=True)
                lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
            if self.table.header_rows:
                lines.append("|" + "---|" * self.table.n_cols)
        return "\n".join(lines)

    def row(self, row: list[str]) -> str:
        if not self.wide:
            return "| " + " | ".join(_md_cell(c) for c in dedupe_row(row)) + " |"
        cells = dedupe_row(row)
        if not self.table.header_rows:
            return " | ".join(c for c in cells if c)
        return "; ".join(
            f"{n}: {_md_cell(c)}" for n, c in zip(self.names, cells, strict=False) if c
        )

    def text(self, rows: Iterable[list[str]]) -> str:
        return "\n".join([self.head(), *(self.row(r) for r in rows)])


def table_problems(table: Table, config: ChunkingConfig) -> list[str]:
    """Reasons a parsed table looks broken (empty if it looks fine)."""
    problems = []
    rows = [dedupe_row(r) for r in table.rows]
    largest = max((count_tokens(c) for r in rows for c in r), default=0)
    if largest > config.broken_cell_max:
        problems.append(f"a cell has {largest} tokens")
    cells = [c for r in rows for c in r]
    mostly_empty = cells and sum(1 for c in cells if not c) / len(cells) > 0.6
    if mostly_empty and len(rows) <= 8:  # long checklists have blank score cells by design
        problems.append("small and mostly empty: a figure or text box, not a table?")
    return problems


def _row_units(rows: list[list[str]]) -> list[list[list[str]]]:
    """Group rows that share a first-column value (a food category, an age group) so a
    row group never splits one. Tables without such runs give one unit per row."""
    units: list[list[list[str]]] = []
    for row in rows:
        key = row[0] if row else ""
        if units and key and units[-1][0] and units[-1][0][0] == key:
            units[-1].append(row)
        else:
            units.append([row])
    return units


# --- The chunker --------------------------------------------------------------------


class Chunker:
    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()

    # -- entry point --

    def chunk(self, tree: Document, doc: SourceDocument) -> tuple[list[Chunk], ChunkReport]:
        report = ChunkReport(tree.doc_id)
        pieces: list[_Piece] = []
        for section in tree.sections:
            pieces += self._section(section, [section.heading], report)
        return self._finish(pieces, doc), report

    # -- sections --

    def _section(self, section: Section, path: list[str], report: ChunkReport) -> list[_Piece]:
        pieces = self._blocks(section.blocks, path, section, report)
        run: list[Section] = []
        for child in section.children:
            if self._is_small(child):
                run.append(child)
                continue
            pieces += self._merge_run(run, section, path, report)
            run = []
            pieces += self._section(child, [*path, child.heading], report)
        pieces += self._merge_run(run, section, path, report)
        return pieces

    def _is_small(self, section: Section) -> bool:
        if section.children or any(
            b.type in (BlockType.TABLE, BlockType.RECOMMENDATION) for b in section.blocks
        ):
            return False
        size = sum(count_tokens(block_text(b)) for b in section.blocks)
        return size < self.config.small_section_max

    def _merge_run(
        self, run: list[Section], parent: Section, path: list[str], report: ChunkReport
    ) -> list[_Piece]:
        """Merge a run of small sibling sections under their parent (3.3). A run of one
        is chunked as a normal section."""
        if len(run) == 1:
            return self._section(run[0], [*path, run[0].heading], report)
        pieces: list[_Piece] = []
        texts: list[str] = []
        group: list[Section] = []

        def emit() -> None:
            if group:
                blocks = [b for s in group for b in s.blocks]
                pieces.append(_Piece("\n\n".join(texts), _kind(blocks), blocks, path, group[0],
                                     [s.heading for s in group]))  # fmt: skip
                texts.clear()
                group.clear()

        for small in run:
            body = "\n\n".join(block_text(b) for b in small.blocks)
            text = f"{small.heading}\n{body}" if body else small.heading
            if texts and count_tokens("\n\n".join([*texts, text])) > self.config.prose_max:
                emit()
            texts.append(text)
            group.append(small)
        emit()
        return pieces

    # -- blocks of one section --

    def _blocks(
        self, blocks: list[Block], path: list[str], section: Section, report: ChunkReport
    ) -> list[_Piece]:
        """Pack a section's own blocks (3.2), handing tables, recommendations and long
        lists to their own handlers."""
        pieces: list[_Piece] = []
        buffer: list[Block] = []
        overlap_only = False  # the buffer holds only a paragraph already emitted as overlap

        def flush(keep_overlap: bool = False) -> None:
            nonlocal overlap_only
            if buffer and not overlap_only:
                pieces.append(self._prose_piece(buffer, path, section))
            last = buffer[-1] if buffer else None
            buffer.clear()
            overlap_only = False
            if (
                keep_overlap
                and last is not None
                and last.type is BlockType.PROSE
                and count_tokens(last.text) <= self.config.overlap_max
            ):
                buffer.append(last)  # repeat the last paragraph at the start of the next chunk
                overlap_only = True

        for block in blocks:
            if block.type is BlockType.RECOMMENDATION:
                flush()
                pieces += self._recommendation(block, path, section, report)
            elif block.type is BlockType.TABLE:
                flush()
                pieces += self._table(block, path, section, report)
            elif (
                block.type is BlockType.LIST
                and count_tokens(block_text(block)) > self.config.prose_max
            ):
                lead_in = None
                if buffer and buffer[-1].type is BlockType.PROSE and buffer[-1].text.endswith(":"):
                    lead_in = buffer.pop()
                    overlap_only = overlap_only and bool(buffer)
                flush()
                pieces += self._long_list(block, lead_in, path, section, report)
            else:
                if buffer and self._size(buffer, block) > self.config.prose_max:
                    flush(keep_overlap=True)
                    if buffer and self._size(buffer, block) > self.config.prose_max:
                        buffer.clear()  # the overlap paragraph doesn't fit with this block
                        overlap_only = False
                buffer.append(block)
                overlap_only = False
        flush()
        return pieces

    def _size(self, buffer: list[Block], block: Block) -> int:
        return count_tokens("\n\n".join(block_text(b) for b in [*buffer, block]))

    def _prose_piece(self, blocks: list[Block], path: list[str], section: Section) -> _Piece:
        text = "\n\n".join(block_text(b) for b in blocks)
        return _Piece(text, _kind(blocks), list(blocks), path, section)

    # -- lists (3.7) --

    def _long_list(
        self,
        block: Block,
        lead_in: Block | None,
        path: list[str],
        section: Section,
        report: ChunkReport,
    ) -> list[_Piece]:
        limit = self.config.prose_max
        head = lead_in.text if lead_in else ""
        lines: list[str] = []
        for item in block.items:
            line = list_item_line(item)
            if count_tokens(line) > limit - count_tokens(head):
                report.split_items += 1
                lines += _pack(split_sentences(line), limit - count_tokens(head))
            else:
                lines.append(line)
        source = [lead_in, block] if lead_in else [block]
        pieces = []
        for group in _pack(lines, limit - count_tokens(head), sep="\n"):
            text = f"{head}\n{group}" if head else group
            pieces.append(_Piece(text, BlockType.LIST, source, path, section))
        return pieces

    # -- recommendations (3.4) --

    def _recommendation(
        self, block: Block, path: list[str], section: Section, report: ChunkReport
    ) -> list[_Piece]:
        limit = self.config.recommendation_max
        if count_tokens(block.text) <= limit:
            return [_Piece(block.text, BlockType.RECOMMENDATION, [block], path, section)]
        report.split_recommendations += 1
        title, *points = block.text.split("\n")
        groups = _pack(points or split_sentences(title), limit - count_tokens(title), sep="\n")
        return [_Piece(f"{title}\n{g}", BlockType.RECOMMENDATION, [block], path, section)
                for g in groups]  # fmt: skip

    # -- tables (3.5, 3.6) --

    def _table(
        self, block: Block, path: list[str], section: Section, report: ChunkReport
    ) -> list[_Piece]:
        table = block.table
        assert table is not None
        table_id = table.table_id or f"{slugify(path[-1])}-table"
        if problems := table_problems(table, self.config):
            report.flagged_tables[table_id] = problems
        if not table.header_rows:
            report.headerless_tables.append(table_id)
        title = table.caption or f"Table: {path[-1]}"
        writer = TableWriter(table, title, self.config)

        whole = writer.text(table.rows)
        if count_tokens(whole) <= self.config.table_whole_max:
            return [_Piece(whole, BlockType.TABLE, [block], path, section, table_id=table_id)]

        budget = self.config.table_group_max - count_tokens(writer.head())
        groups: list[list[list[str]]] = [[]]
        size = 0
        for unit in _row_units(table.rows):
            unit_size = sum(count_tokens(writer.row(r)) for r in unit)
            if unit_size > budget:  # a category too big for one group: split it by rows
                report.split_categories.append(f"{table_id}: {unit[0][0]}")
                for row in unit:
                    row_size = count_tokens(writer.row(row))
                    if groups[-1] and size + row_size > budget:
                        groups.append([])
                        size = 0
                    groups[-1].append(row)
                    size += row_size
                continue
            if groups[-1] and size + unit_size > budget:
                groups.append([])
                size = 0
            groups[-1].extend(unit)
            size += unit_size
        report.split_tables[table_id] = len(groups)
        return [
            _Piece(writer.text(g), BlockType.TABLE, [block], path, section, table_id=table_id)
            for g in groups
        ]

    # -- metadata (3.8) --

    def _finish(self, pieces: list[_Piece], doc: SourceDocument) -> list[Chunk]:
        if doc.year is None or doc.retrieval_date is None:
            raise ValueError(f"{doc.doc_id} needs a year and a retrieval_date to be chunked")
        header_doc = search_header(doc)
        seen: Counter[str] = Counter()
        chunks = []
        for piece in pieces:
            text = piece.text.strip()
            if not text:
                continue
            slug = slugify(piece.path[-1])
            seen[slug] += 1
            pages = [p for b in piece.blocks for p in (b.page, b.page_end) if p is not None]
            page_start = min(pages) if pages else None
            page_end = max(pages) if pages else None
            section_line = f"[Section: {' > '.join(piece.path)}]"
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}:{slug}:{seen[slug]}",
                    doc_id=doc.doc_id,
                    doc_title=doc.title,
                    publisher=doc.publisher,
                    year=doc.year,
                    source_url=doc.source_url,
                    retrieval_date=doc.retrieval_date,
                    section_path=piece.path,
                    section_heading=piece.path[-1],
                    subsections=piece.subsections,
                    page_start=page_start,
                    page_end=page_end,
                    deep_link=deep_link(doc, page_start, piece.section.anchor),
                    block_type=piece.block_type,
                    table_id=piece.table_id,
                    domain=doc.domain,
                    text=text,
                    embed_text=search_text(f"{header_doc}\n{section_line}\n{text}"),
                    token_count=count_tokens(text),
                    ocr=any(b.ocr for b in piece.blocks),
                )
            )
        return chunks


def search_header(doc: SourceDocument) -> str:
    """Short document label for the contextual header, e.g. "[FSSAI FSMS Milk · 2018]".

    The registry `short_name` keeps the header to ~10-15 tokens; the full title and
    publisher would add 40-50 identical tokens to every chunk of a document, which
    blurs its vectors. Citations still use the full title and publisher.
    """
    label = doc.short_name
    if str(doc.year) not in label:
        label = f"{label} · {doc.year}"
    return f"[{label}]"


_PRIVATE_USE = re.compile("[\ue000-\uf8ff]")


def search_text(text: str) -> str:
    """Normalise text used only for search (embeddings and BM25), not shown to the LLM.

    "º" (ordinal indicator, typed as a degree sign in the FSSAI documents) becomes
    "°", symbol-font bullets in the private-use area are removed, and runs of spaces
    collapse.
    """
    text = _PRIVATE_USE.sub(" ", text.replace("º", "°"))
    return re.sub(r"[ \t]+", " ", re.sub(r" *\n *", "\n", text)).strip()


def deep_link(doc: SourceDocument, page: int | None, anchor: str | None) -> str:
    """`source_url#page=N` when the source is a PDF; `#anchor` for HTML sections.

    Some PDFs are cited through a publication page (JECFA's source_url is WHO's
    page, not the PDF), where a page fragment means nothing; those get the plain URL.
    """
    url = str(doc.source_url)
    if doc.format is DocumentFormat.PDF:
        is_pdf_url = url.lower().split("?")[0].endswith(".pdf")
        return f"{url}#page={page}" if is_pdf_url and page else url
    return f"{url}#{anchor}" if anchor else url


def _kind(blocks: list[Block]) -> BlockType:
    return (
        BlockType.LIST
        if blocks and all(b.type is BlockType.LIST for b in blocks)
        else BlockType.PROSE
    )


def _pack(parts: list[str], limit: int, sep: str = " ") -> list[str]:
    """Join parts in order into groups of at most `limit` tokens (a part larger than the
    limit stays whole)."""
    groups: list[list[str]] = []
    for part in parts:
        if groups and count_tokens(sep.join([*groups[-1], part])) <= limit:
            groups[-1].append(part)
        else:
            groups.append([part])
    return [sep.join(g) for g in groups]


# --- Running over the corpus (3.9) -------------------------------------------------

DEFAULT_CHUNKS_DIR = PROJECT_ROOT / "corpus" / "chunks"


def chunk_document(
    doc: SourceDocument,
    chunker: Chunker | None = None,
    parsed_dir: Path = DEFAULT_PARSED_DIR,
    raw_dir: Path = DEFAULT_RAW_DIR,
) -> tuple[list[Chunk], ChunkReport]:
    """Chunk a document from its saved tree, re-parsing first if the tree is stale."""
    tree = load_or_parse(doc, parsed_dir, raw_dir)
    return (chunker or Chunker()).chunk(tree, doc)


def write_chunks(chunks: list[Chunk], path: Path) -> None:
    """One chunk per line (JSONL), written atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8")
    tmp.replace(path)


def read_chunks(path: Path) -> list[Chunk]:
    with path.open(encoding="utf-8") as f:
        return [Chunk.model_validate_json(line) for line in f if line.strip()]
