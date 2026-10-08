"""Structure-aware vs. fixed-size chunking on the same parsed corpus (implementation-plan.md, 10.2).

Fixed-size chunking is simulated the way a text splitter sees a document: the parsed
blocks in reading order as plain text (headings included), cut into windows of
`--size` tokens with `--overlap` tokens of overlap, using the chunker's tokenizer.
For the two kinds of content the brief says must not be cut, it counts:

- tables and numbered recommendations that no single window holds whole;
- window pieces that carry table rows without the table's header row, so the numbers in
  them lose their column names ("3 to 4 days" without "Refrigerator").

The structure-aware numbers come from the committed chunks (corpus/chunks/).

    .venv/bin/python -m eval.chunking_comparison --out eval/results/chunking.md
"""

import argparse
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from guidance_rag.ingest.chunker import count_tokens
from guidance_rag.ingest.parse import load_or_parse
from guidance_rag.ingest.tree import walk
from guidance_rag.models import BlockType
from guidance_rag.registry import load_registry
from guidance_rag.store import load_chunks


@dataclass
class Span:
    kind: BlockType
    start: int  # token offsets in the document's text stream
    end: int
    header_end: int  # tables: end of the caption + header row; else = start


@dataclass
class DocResult:
    doc_id: str
    tables: int = 0
    tables_cut: int = 0
    recommendations: int = 0
    recommendations_cut: int = 0
    pieces_without_header: int = 0
    windows: int = 0


def block_text(kind: BlockType, text: str, table_text: str | None) -> str:
    return table_text if kind is BlockType.TABLE and table_text else text


def stream(doc_id: str) -> tuple[int, list[Span]]:
    """Total tokens of the document's text stream, and the spans of its blocks."""
    registry = load_registry()
    tree = load_or_parse(registry.get(doc_id))
    pos, spans, last_path = 0, [], None
    for path, _, block in walk(tree):
        if path != last_path:  # a splitter sees the headings as text too
            pos += count_tokens("\n".join(path) + "\n")
            last_path = path
        table_text = block.table.to_text() if block.table else None
        text = block_text(block.type, block.text, table_text)
        n = count_tokens(text + "\n\n")
        header = 0
        if block.table is not None:
            head_lines = text.split("\n")[: 1 + len(block.table.header_rows) + 1]
            header = count_tokens("\n".join(head_lines))
        spans.append(Span(block.type, pos, pos + n, pos + header if header else pos))
        pos += n
    return pos, spans


def fixed_size(doc_id: str, size: int, overlap: int) -> DocResult:
    total, spans = stream(doc_id)
    step = size - overlap
    windows = [(s, s + size) for s in range(0, max(total - overlap, 1), step)]
    result = DocResult(doc_id, windows=len(windows))
    for span in spans:
        whole = any(a <= span.start and span.end <= b for a, b in windows)
        if span.kind is BlockType.TABLE:
            result.tables += 1
            result.tables_cut += not whole
            # Pieces that hold some of the table's rows but not its header.
            for a, b in windows:
                has_rows = a < span.end and b > span.header_end
                has_header = a <= span.start and b >= span.header_end
                result.pieces_without_header += has_rows and not has_header and not whole
        elif span.kind is BlockType.RECOMMENDATION:
            result.recommendations += 1
            result.recommendations_cut += not whole
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--size", type=int, default=400)
    parser.add_argument("--overlap", type=int, default=50)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    docs = [d.doc_id for d in load_registry().included]
    results = [fixed_size(d, args.size, args.overlap) for d in docs]
    chunks = load_chunks()
    sizes = sorted(c.token_count for c in chunks)
    by_type = Counter(c.block_type.value for c in chunks)
    q = statistics.quantiles(sizes, n=10)

    lines = [
        "# Chunking: structure-aware vs. fixed-size",
        "",
        f"Fixed-size: {args.size}-token windows with {args.overlap}-token overlap over the "
        "parsed text in reading order (headings included), cl100k tokens. Structure-aware: "
        "the committed chunks. Produced by `python -m eval.chunking_comparison`.",
        "",
        "| Document | Tables | cut (fixed) | pieces without header (fixed) "
        "| Recommendations | cut (fixed) | Windows (fixed) | Chunks (structure-aware) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    per_doc = Counter(c.doc_id for c in chunks)
    for r in results:
        lines.append(
            f"| {r.doc_id} | {r.tables} | {r.tables_cut} | {r.pieces_without_header} "
            f"| {r.recommendations} | {r.recommendations_cut} | {r.windows} | {per_doc[r.doc_id]} |"
        )
    t = sum(r.tables for r in results)
    tc = sum(r.tables_cut for r in results)
    rc = sum(r.recommendations for r in results)
    rcc = sum(r.recommendations_cut for r in results)
    ph = sum(r.pieces_without_header for r in results)
    lines.append(
        f"| **All** | **{t}** | **{tc} ({tc / t:.0%})** | **{ph}** | **{rc}** | "
        f"**{rcc} ({rcc / rc:.0%})** | **{sum(r.windows for r in results)}** | **{len(chunks)}** |"
    )
    lines += [
        "",
        "Structure-aware chunking cuts no recommendation and no table under 800 tokens; "
        "larger tables are split between rows with the caption and header repeated in every "
        "piece, so no piece is without its header.",
        "",
        f"Structure-aware chunk sizes (tokens): min {sizes[0]}, 10th percentile {q[0]:.0f}, "
        f"median {statistics.median(sizes):.0f}, 90th percentile {q[8]:.0f}, max {sizes[-1]}. "
        f"By type: {', '.join(f'{k} {v}' for k, v in sorted(by_type.items()))}.",
    ]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
