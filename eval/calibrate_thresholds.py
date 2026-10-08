"""Calibrate the not-in-corpus thresholds (implementation-plan.md, 7.5).

Retrieves once per golden question (answerable and not-in-corpus) with thresholds off,
keeping every rerank score, then sweeps `tau_doc` x `tau_answer` over the saved scores
(no model calls): a question passes the score gate when evidence is selected at `tau_doc`
and the best score reaches `tau_answer`. Reports, for each pair, the answer rate on
answerable questions and the false-answer rate on not-in-corpus questions.

The pick: zero false answers, then the highest answer rate; among ties, the current
`tau_doc` and the `tau_answer` with the widest margin on both sides (the midpoint of the
gap between the two groups' best scores).

    .venv/bin/python -m eval.calibrate_thresholds --out eval/results/thresholds.md
    .venv/bin/python -m eval.calibrate_thresholds --end-to-end   # + full pipeline at the pick

`--end-to-end` runs the real pipeline (Groq evidence check and generator) at the chosen
values and checks the Phase 7 exit criteria. Needs GROQ_API_KEY; replies are cached.
"""

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from eval.golden import ANSWERABLE_CATEGORIES, GoldenCategory, GoldenEntry, load_golden
from guidance_rag.config import RetrievalConfig, get_settings
from guidance_rag.models import AnswerStatus, Chunk, Evidence, ScoredChunk
from guidance_rag.query.analyzer import QueryAnalyzer
from guidance_rag.query.retriever import load_retriever, select
from guidance_rag.registry import load_registry

TAU_DOC_GRID = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4]
TAU_ANSWER_GRID = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6]


@dataclass
class Scored:
    q: GoldenEntry
    evidence: Evidence  # thresholds off: every pool chunk with its rerank score
    answerable: bool

    @property
    def best(self) -> float:
        return self.evidence.best_score or 0.0


def passes(s: Scored, chunks: dict[str, Chunk], tau_doc: float, tau_answer: float) -> bool:
    """Would the score gate let this question through?"""
    config = RetrievalConfig()
    ranked = [ScoredChunk(chunk=chunks[c], score=v) for c, v in s.evidence.ranked]
    docs = select(ranked, config, tau_doc, min(config.tau_doc_extra, tau_doc))
    return bool(docs) and s.best >= tau_answer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--end-to-end", action="store_true", help="also run the full pipeline")
    parser.add_argument("--out", type=Path, help="write the report to this Markdown file")
    args = parser.parse_args()

    golden = load_golden()
    questions = [
        q
        for q in golden.questions
        if q.category in ANSWERABLE_CATEGORIES or q.category is GoldenCategory.NOT_IN_CORPUS
    ]
    analyzer = QueryAnalyzer(load_registry())
    retriever = load_retriever(RetrievalConfig(tau_doc=0.0, tau_doc_extra=0.0))
    scored: list[Scored] = []
    try:
        for q in questions:
            a = analyzer.analyze(q.question, q.doc_filter)
            ev = retriever.retrieve(a.query, a.doc_ids, a.sub_queries)
            scored.append(Scored(q, ev, q.category in ANSWERABLE_CATEGORIES))
        chunks = dict(retriever._chunks)
    finally:
        retriever.close()

    answerable = [s for s in scored if s.answerable]
    negatives = [s for s in scored if not s.answerable]
    lowest_answerable = min(answerable, key=lambda s: s.best)
    highest_negative = max(negatives, key=lambda s: s.best)

    grid: dict[tuple[float, float], tuple[int, int]] = {}
    for td in TAU_DOC_GRID:
        for ta in TAU_ANSWER_GRID:
            ok = sum(passes(s, chunks, td, ta) for s in answerable)
            false = sum(passes(s, chunks, td, ta) for s in negatives)
            grid[(td, ta)] = (ok, false)

    current = RetrievalConfig().tau_doc
    safe = [(k, v) for k, v in grid.items() if v[1] == 0]
    best_rate = max(v[0] for _, v in safe)
    candidates = [k for k, v in safe if v[0] == best_rate]
    pick_doc = current if any(td == current for td, _ in candidates) else candidates[0][0]
    # Widest margin: the midpoint of the gap between the groups, if it keeps the best
    # answer rate with no false answers; else the highest safe grid value.
    midpoint = round((highest_negative.best + lowest_answerable.best) / 2, 2)
    if grid_counts(scored, chunks, pick_doc, midpoint) == (best_rate, 0):
        pick_answer = midpoint
    else:
        pick_answer = max(ta for td, ta in candidates if td == pick_doc)

    lines = [
        "# Threshold calibration (7.5)",
        "",
        f"Golden set v{golden.version}: {len(answerable)} answerable and {len(negatives)} "
        "not-in-corpus questions. Scores are rerank scores "
        f"(`{RetrievalConfig().reranker_model}`), best over the question and its halves.",
        "",
        "## Best score per question",
        "",
        f"- Answerable: lowest **{lowest_answerable.best:.3f}** ({lowest_answerable.q.id}), "
        f"median {sorted(s.best for s in answerable)[len(answerable) // 2]:.3f}",
        f"- Not in corpus: highest **{highest_negative.best:.3f}** ({highest_negative.q.id}); "
        + ", ".join(f"{s.q.id} {s.best:.3f}" for s in negatives),
        f"- Gap between the groups: {highest_negative.best:.3f}–{lowest_answerable.best:.3f}",
        "",
        "## Score gate over the grid",
        "",
        f"Cells: answerable passed / {len(answerable)} · not-in-corpus passed (false answers) "
        f"/ {len(negatives)}. A question passes when evidence is selected at `tau_doc` and "
        "its best score reaches `tau_answer`.",
        "",
        "| tau_doc \\ tau_answer | " + " | ".join(str(t) for t in TAU_ANSWER_GRID) + " |",
        "|---|" + "---:|" * len(TAU_ANSWER_GRID),
    ]
    for td in TAU_DOC_GRID:
        cells = []
        for ta in TAU_ANSWER_GRID:
            ok, false = grid[(td, ta)]
            cell = f"{ok} · {false}"
            cells.append(f"**{cell}**" if (td, ta) == (pick_doc, pick_answer) else cell)
        lines.append(f"| {td} | " + " | ".join(cells) + " |")
    pick_ok, pick_false = grid_counts(scored, chunks, pick_doc, pick_answer)
    lines += [
        "",
        "## Pick",
        "",
        f"`tau_doc` = **{pick_doc}**, `tau_answer` = **{pick_answer}**: "
        f"{pick_ok}/{len(answerable)} answerable pass the score gate, "
        f"{pick_false}/{len(negatives)} false answers.",
    ]

    if args.end_to_end:
        lines += ["", *end_to_end(questions, pick_answer)]

    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


def grid_counts(
    scored: list[Scored], chunks: dict[str, Chunk], td: float, ta: float
) -> tuple[int, int]:
    ok = sum(passes(s, chunks, td, ta) for s in scored if s.answerable)
    false = sum(passes(s, chunks, td, ta) for s in scored if not s.answerable)
    return ok, false


def end_to_end(questions: list[GoldenEntry], tau_answer: float) -> list[str]:
    """The full pipeline at the chosen tau_answer: Phase 7 exit criteria."""
    from guidance_rag.pipeline import load_pipeline

    settings = get_settings().model_copy(update={"tau_answer": tau_answer})
    pipeline = load_pipeline(settings)
    statuses: Counter[str] = Counter()
    wrong: list[str] = []
    refused_answerable: list[str] = []
    try:
        for q in questions:
            answer = pipeline.run(q.question, q.doc_filter)
            statuses[f"{q.category.value}: {answer.status.value}"] += 1
            print(f"{q.id}: {answer.status.value}", file=sys.stderr)
            if q.category is GoldenCategory.NOT_IN_CORPUS:
                listed = answer.refusal is not None and "Searched:" in answer.refusal.message
                if answer.status is not AnswerStatus.NOT_IN_CORPUS or not listed:
                    wrong.append(f"{q.id} → {answer.status.value}")
            elif answer.status is AnswerStatus.NOT_IN_CORPUS:
                refused_answerable.append(q.id)
    finally:
        pipeline.close()
    answerable = sum(q.category in ANSWERABLE_CATEGORIES for q in questions)
    rate = len(refused_answerable) / answerable
    return [
        "## End to end at the pick (score check + LLM evidence check + generator)",
        "",
        "| Category: status | Count |",
        "|---|---:|",
        *[f"| {k} | {v} |" for k, v in sorted(statuses.items())],
        "",
        f"- Not-in-corpus questions answered `not_in_corpus` with the documents listed: "
        f"{'all' if not wrong else 'NOT all: ' + ', '.join(wrong)}",
        f"- Answerable questions wrongly refused: {len(refused_answerable)}/{answerable} "
        f"({rate:.0%}; target ≤ 10%) {', '.join(refused_answerable)}",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
