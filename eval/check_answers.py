"""Check answers from the real model (implementation-plan.md, 6.8).

Runs golden questions through the pipeline's steps one by one and reports, for each:

- what the model proposed, and how many claims tried to cite another document's chunk
  (blending before the validator),
- which claims the validator dropped, and why,
- the final rendered answer, with each claim next to the text of its cited chunks, for
  reading by hand.

Totals at the top: blend rate in the rendered answers (must be 0), proposed blends,
dropped claims by reason, and status counts.

    .venv/bin/python -m eval.check_answers                    # cross-document questions
    .venv/bin/python -m eval.check_answers --all --out eval/results/answers.md

Needs GROQ_API_KEY and the built index. LLM replies are cached in .cache/llm/, so a
re-run costs nothing unless the prompt or evidence changed.
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from eval.golden import ANSWERABLE_CATEGORIES, GoldenCategory, GoldenEntry, load_golden
from guidance_rag.config import get_settings
from guidance_rag.generator import Generator
from guidance_rag.llm import CachedLLM, GroqLLM
from guidance_rag.models import Answer
from guidance_rag.pipeline import Pipeline, RagAnswerer
from guidance_rag.query.analyzer import QueryAnalyzer
from guidance_rag.query.retriever import load_retriever
from guidance_rag.rate_limit import limiter_from_settings
from guidance_rag.registry import load_registry
from guidance_rag.validator import DroppedClaim, validate


class Recorder(Generator):
    """A generator that keeps its last result, so the report can show what was proposed."""

    last = None

    def generate(self, question, evidence):  # type: ignore[no-untyped-def]
        self.last = super().generate(question, evidence)
        self.last_evidence = evidence
        return self.last


def proposed_blends(recorder: Recorder) -> int:
    """Claims that cite at least one chunk of another document than their section's."""
    if not recorder.last:
        return 0
    doc_of = {
        sc.chunk.chunk_id: sc.chunk.doc_id
        for d in recorder.last_evidence.documents
        for sc in d.chunks
    }
    return sum(
        any(doc_of.get(c, s.doc_id) != s.doc_id for c in claim.chunk_ids)
        for s in recorder.last.sections
        for claim in s.claims
    )


def review(
    q: GoldenEntry, answer: Answer, chunks: dict[str, str], dropped: list[DroppedClaim]
) -> list[str]:
    lines = [f"### {q.id} ({q.category}): {q.question}", "", f"**Status:** {answer.status.value}"]
    if answer.refusal:
        lines += ["", f"> {answer.refusal.message}"]
    if q.expected_answer_notes:
        lines += ["", f"**Expected (golden notes):** {q.expected_answer_notes}"]
    for section in answer.sections:
        lines += ["", f"**{section.doc_id}**"]
        for claim in section.claims:
            lines.append(f"- {claim.text}")
            for cid in claim.chunk_ids:
                snippet = " ".join(chunks.get(cid, "").split())[:400]
                lines.append(f"    - `{cid}`: {snippet}…")
    if answer.not_covered:
        lines += ["", f"**Not covered:** {answer.not_covered}"]
    if dropped:
        lines += ["", "**Dropped by the validator:**"]
        lines += [f"- ({d.doc_id}) {d.text} — *{d.reason}*" for d in dropped]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--all", action="store_true", help="every answerable golden question")
    parser.add_argument("--out", type=Path, help="write the report to this Markdown file")
    args = parser.parse_args()

    settings = get_settings()
    registry = load_registry(settings.registry_path)
    limiter = limiter_from_settings(settings)
    llm = CachedLLM(GroqLLM(api_key=settings.groq_api_key.get_secret_value(), limiter=limiter))
    recorder = Recorder(llm, settings.generator_model)
    answerer = RagAnswerer(QueryAnalyzer(registry), load_retriever(), recorder, registry)
    pipeline = Pipeline(answerer)  # the input guard runs; the classifier isn't needed here

    golden = load_golden()
    if args.all:
        questions = [q for q in golden.questions if q.category in ANSWERABLE_CATEGORIES]
    else:
        questions = golden.by_category(GoldenCategory.CROSS_DOC)

    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    proposed = blended_out = rendered_claims = 0
    reviews: list[str] = []
    timings = []
    try:
        for q in questions:
            recorder.last = None
            start = time.perf_counter()
            answer = pipeline.run(q.question, q.doc_filter)
            timings.append(time.perf_counter() - start)
            statuses[answer.status.value] += 1
            proposed += proposed_blends(recorder)
            chunks: dict[str, str] = {}
            dropped: list[DroppedClaim] = []
            if recorder.last:
                ev = recorder.last_evidence
                chunks = {sc.chunk.chunk_id: sc.chunk.text for d in ev.documents for sc in d.chunks}
                dropped = validate(recorder.last.sections, ev).dropped
                for d in dropped:
                    reasons[d.reason.split(":")[0].split(" (")[0]] += 1
            for s in answer.sections:
                for claim in s.claims:
                    rendered_claims += 1
                    blended_out += any(c.split(":")[0] != s.doc_id for c in claim.chunk_ids)
            reviews += [*review(q, answer, chunks, dropped), ""]
            print(f"{q.id}: {answer.status.value}", file=sys.stderr)
    finally:
        answerer.close()

    timings.sort()
    summary = [
        "# Answer check (6.8)",
        "",
        f"Model: `{settings.generator_model}` on Groq. Questions: {len(questions)}. "
        f"LLM cache: {llm.hits} hits, {llm.misses} calls.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Blend rate in rendered answers | {blended_out}/{rendered_claims} claims |",
        f"| Claims the model proposed citing another document | {proposed} |",
        f"| Status | {', '.join(f'{k} {v}' for k, v in statuses.most_common())} |",
        f"| Claims dropped by the validator | {sum(reasons.values())} "
        f"({', '.join(f'{k}: {v}' for k, v in reasons.most_common()) or 'none'}) |",
        f"| Rendered claims | {rendered_claims} |",
        f"| Time per question (median / max, incl. retrieval) "
        f"| {timings[len(timings) // 2]:.1f} s / {timings[-1]:.1f} s |",
        "",
        "## Answers with their cited text",
        "",
    ]
    text = "\n".join(summary + reviews)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
