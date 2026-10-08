"""Chunk QC report (implementation-plan.md, 3.9): one Markdown file per document."""

from collections import Counter
from pathlib import Path

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.ingest.chunker import ChunkReport
from guidance_rag.models import Chunk

DEFAULT_QC_DIR = PROJECT_ROOT / "corpus" / "qc"

SIZE_BUCKETS = [(0, 50), (50, 100), (100, 200), (200, 400), (400, 600), (600, 800), (800, 1000)]


def _bucket(tokens: int) -> str:
    for low, high in SIZE_BUCKETS:
        if low <= tokens < high:
            return f"{low}-{high}"
    return "1000+"


def _preview(chunk: Chunk, width: int = 90) -> str:
    text = " ".join(chunk.text.split())
    return (text[:width] + "…" if len(text) > width else text).replace("|", "/")


def qc_report(chunks: list[Chunk], report: ChunkReport) -> str:
    sizes = sorted(c.token_count for c in chunks)
    lines = [f"# Chunk QC: {report.doc_id}", ""]
    if not sizes:
        return "\n".join([*lines, "No chunks.", ""])
    lines += [
        f"- Chunks: **{len(chunks)}**, tokens: median {sizes[len(sizes) // 2]}, "
        f"max {sizes[-1]}, total {sum(sizes)}",
        f"- Empty chunks: {sum(1 for c in chunks if not c.text.strip())}",
        f"- From OCR: {sum(1 for c in chunks if c.ocr)}",
        "",
        "## Chunks per block type",
        "",
        "| Block type | Chunks |",
        "|---|---:|",
    ]
    for kind, n in sorted(Counter(c.block_type.value for c in chunks).items()):
        lines.append(f"| {kind} | {n} |")

    buckets = Counter(_bucket(s) for s in sizes)
    lines += ["", "## Size histogram (tokens)", "", "| Tokens | Chunks |", "|---|---:|"]
    for low, high in [*SIZE_BUCKETS, (1000, 0)]:
        label = f"{low}-{high}" if high else "1000+"
        lines.append(f"| {label} | {buckets.get(label, 0)} |")

    by_size = sorted(chunks, key=lambda c: c.token_count)
    for title, picked in [
        ("5 largest chunks", by_size[::-1][:5]),
        ("5 smallest chunks", by_size[:5]),
    ]:
        lines += ["", f"## {title}", "", "| Tokens | Chunk | Starts with |", "|---:|---|---|"]
        lines += [f"| {c.token_count} | `{c.chunk_id}` | {_preview(c)} |" for c in picked]

    lines += ["", "## Tables", ""]
    lines.append(
        "- Split into row groups: "
        + (", ".join(f"`{t}` ({n})" for t, n in report.split_tables.items()) or "none")
    )
    lines.append(
        "- Categories too large for one group (split by rows): "
        + (", ".join(report.split_categories) or "none")
    )
    lines.append(
        "- Without a header row (an override CSV can add one): "
        + (", ".join(f"`{t}`" for t in report.headerless_tables) or "none")
    )
    if report.flagged_tables:
        lines += ["", "### Flagged as broken (fix with an override or `drop_tables`)", ""]
        lines += [f"- `{t}`: {'; '.join(r)}" for t, r in report.flagged_tables.items()]
    else:
        lines.append("- Flagged as broken: none")
    lines += [
        "",
        "## Other splits",
        "",
        f"- List items longer than a chunk, split at sentences: {report.split_items}",
        f"- Recommendations over the size guard, split at bullets: {report.split_recommendations}",
        "",
    ]
    return "\n".join(lines)


def write_qc(chunks: list[Chunk], report: ChunkReport, qc_dir: Path = DEFAULT_QC_DIR) -> Path:
    qc_dir.mkdir(parents=True, exist_ok=True)
    path = qc_dir / f"{report.doc_id}.md"
    path.write_text(qc_report(chunks, report), encoding="utf-8")
    return path
