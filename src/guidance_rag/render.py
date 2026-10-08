"""Renderer: validated claims to the final answer (implementation-plan.md, 6.6; §6.7, §10).

Citation fields (title, publisher, year, section, page, link) come only from chunk
metadata, never from LLM text. Citations are numbered in reading order; each document
gets its own section, in the order given (best rerank score first). A multi-document
answer ends with a fixed closing line, never an LLM summary that could blend sources.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from guidance_rag.models import Answer, AnswerStatus, Chunk, Citation, Claim, DocAnswer

CLOSING_LINE = "These are separate recommendations from different authorities."


def citation_for(n: int, chunk: Chunk) -> Citation:
    return Citation(
        n=n,
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        doc_title=chunk.doc_title,
        publisher=chunk.publisher,
        year=chunk.year,
        section=" > ".join(chunk.section_path),
        page=chunk.page_start,
        url=chunk.deep_link,
        retrieval_date=chunk.retrieval_date,
    )


def order_sections(sections: Sequence[DocAnswer], doc_order: Sequence[str]) -> list[DocAnswer]:
    """One section per document (claims of repeated doc_ids merged), in `doc_order`."""
    merged: dict[str, list[Claim]] = {}
    for s in sections:
        merged.setdefault(s.doc_id, []).extend(s.claims)
    rank = {d: i for i, d in enumerate(doc_order)}
    ordered = sorted(merged, key=lambda d: rank.get(d, len(rank)))
    return [DocAnswer(doc_id=d, claims=merged[d]) for d in ordered]


def render_answer(
    sections: Sequence[DocAnswer],
    chunks: Mapping[str, Chunk],
    trace_id: str,
    doc_order: Sequence[str] = (),
    docs_searched: Sequence[str] = (),
    status: AnswerStatus = AnswerStatus.ANSWERED,
    not_covered: str | None = None,
) -> Answer:
    """The final answer: sections, numbered citations and Markdown."""
    sections = order_sections(sections, doc_order)
    numbers: dict[str, int] = {}
    citations: list[Citation] = []
    for section in sections:
        for claim in section.claims:
            for chunk_id in claim.chunk_ids:
                if chunk_id not in numbers:
                    numbers[chunk_id] = len(numbers) + 1
                    citations.append(citation_for(numbers[chunk_id], chunks[chunk_id]))

    lines: list[str] = []
    for section in sections:
        first = chunks[section.claims[0].chunk_ids[0]]
        lines.append(f"**{first.doc_title} — {first.publisher} ({first.year})**")
        for claim in section.claims:
            marks = "".join(f"[{numbers[c]}]" for c in claim.chunk_ids)
            lines.append(f"- {claim.text} {marks}")
        lines.append("")
    if len(sections) > 1:
        lines += [CLOSING_LINE, ""]
    if not_covered:
        lines += [f"_Not covered by these documents: {not_covered}_", ""]
    lines.append("---")
    for c in citations:
        page = f" · p. {c.page}" if c.page else ""
        lines.append(
            f"[{c.n}] {c.doc_title} · {c.publisher} · {c.year} · §{c.section}{page} · {c.url}"
        )

    return Answer(
        status=status,
        sections=list(sections),
        citations=citations,
        docs_searched=list(docs_searched),
        not_covered=not_covered,
        markdown="\n".join(lines),
        trace_id=trace_id,
    )


def api_response(answer: Answer) -> dict[str, Any]:
    """The answer in the API shape of §10: claims carry citation numbers."""
    number = {c.chunk_id: c.n for c in answer.citations}
    meta = {c.doc_id: c for c in answer.citations}
    sections = []
    for s in answer.sections:
        doc = meta.get(s.doc_id)
        sections.append(
            {
                "doc_id": s.doc_id,
                "doc_title": doc.doc_title if doc else None,
                "publisher": doc.publisher if doc else None,
                "year": doc.year if doc else None,
                "claims": [
                    {"text": c.text, "citations": [number[i] for i in c.chunk_ids if i in number]}
                    for c in s.claims
                ],
            }
        )
    return {
        "status": answer.status.value,
        "refusal": answer.refusal.model_dump(mode="json") if answer.refusal else None,
        "sections": sections,
        "citations": [
            {
                "n": c.n,
                "doc_title": c.doc_title,
                "publisher": c.publisher,
                "year": c.year,
                "section": c.section,
                "page": c.page,
                "url": c.url,
                "retrieval_date": c.retrieval_date.isoformat(),
            }
            for c in answer.citations
        ],
        "not_covered": answer.not_covered,
        "docs_searched": answer.docs_searched,
        "trace_id": answer.trace_id,
    }
