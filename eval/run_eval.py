"""Full eval of the assistant on the golden set (implementation-plan.md, 9.1).

Sends every golden question through the real pipeline (input guard, classifier, analyzer,
retriever, sufficiency gate, generator, validator, output guard, renderer) with a trace,
and reports:

- Retrieval Recall@10 (a gold chunk in the top 10 of the final ranking)
- correct status per category, and correct cited documents
- out-of-scope and not-in-corpus refusal recall
- false refusals on answerable questions, and on near misses
- blend rate and uncited claims in the rendered answers
- citation precision from the LLM judge (--judge; eval/judge.py)
- latency p50 / p95

Each failure is put down to the stage where it went wrong, from its trace (9.3).

    .venv/bin/python -m eval.run_eval                      # dev split (the default)
    .venv/bin/python -m eval.run_eval --split all --judge --out eval/report.md
    .venv/bin/python -m eval.run_eval --set eval/redteam.yaml --split all
    .venv/bin/python -m eval.run_eval --check              # exit 1 if a target is missed
    .venv/bin/python -m eval.run_eval --no-cache --id sd-01 --id cd-01   # live latency

Questions marked `holdout: true` in golden.yaml are only scored with --split holdout or
all, never while fixing failures. LLM replies come from .cache/llm/ when the same request
was made before, so re-runs are repeatable and cost nothing; latency is reported over
questions answered live, minus time spent waiting on the Groq quota. --no-cache answers
everything live (with a fresh, empty cache) to measure latency.
"""

import argparse
import json
import logging
import statistics
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from eval.golden import ANSWERABLE_CATEGORIES, GOLDEN_PATH, GoldenCategory, GoldenEntry, load_golden
from eval.judge import Judge, JudgedClaim, Verdict
from guidance_rag.config import PROJECT_ROOT, Settings, get_settings
from guidance_rag.llm import CachedLLM, GroqLLM, LLMError
from guidance_rag.models import Answer, AnswerStatus
from guidance_rag.rate_limit import RateLimiter, RateLimits
from guidance_rag.store import load_chunks
from guidance_rag.tracing import Trace, TraceLog

log = logging.getLogger(__name__)

DEFAULT_TRACES = PROJECT_ROOT / "logs" / "eval_traces.jsonl"
REFUSALS = {AnswerStatus.NOT_IN_CORPUS.value, AnswerStatus.OUT_OF_SCOPE.value}
ANSWERS = {AnswerStatus.ANSWERED.value, AnswerStatus.PARTIAL.value}
ERROR = "error"  # the pipeline raised (e.g. the answer model was unavailable)
K = 10


# --- Targets (Phase 9 exit criteria) ------------------------------------------------------


@dataclass(frozen=True)
class Target:
    name: str
    goal: str
    passes: Callable[[float], bool]


TARGETS = {
    "recall_at_10": Target("Retrieval Recall@10", "≥ 0.90", lambda v: v >= 0.90),
    "oos_recall": Target("Out-of-scope refusal recall", "100%", lambda v: v >= 1.0),
    "nic_recall": Target("Not-in-corpus refusal recall", "≥ 95%", lambda v: v >= 0.95),
    "false_refusal": Target("False refusal on answerable questions", "≤ 10%", lambda v: v <= 0.10),
    "citation_precision": Target("Citation precision (judged)", "≥ 0.95", lambda v: v >= 0.95),
    "blend_rate": Target("Blend rate", "0", lambda v: v == 0),
    "uncited_claims": Target("Claims without citation in output", "0", lambda v: v == 0),
    "p95_latency_s": Target("p95 latency", "≤ 8 s", lambda v: v <= 8.0),
}


# --- One question -----------------------------------------------------------------------


@dataclass
class Outcome:
    entry: GoldenEntry
    status: str  # an AnswerStatus value, or "error"
    refusal: str | None
    cited_docs: list[str]
    claims: list[tuple[str, list[str]]]  # (section doc_id, cited doc_ids) per rendered claim
    trace: dict[str, Any]
    latency_s: float
    wait_s: float  # spent waiting on the Groq quota
    llm_hits: int
    llm_misses: int
    answer: Answer | None = None
    judged: list[JudgedClaim] = field(default_factory=list)

    @property
    def live(self) -> bool:
        """Answered with every LLM call sent to Groq (none from the cache, no error), so
        its latency is real."""
        return self.llm_misses > 0 and self.llm_hits == 0 and self.status != ERROR

    @property
    def status_ok(self) -> bool:
        e = self.entry
        if e.category in ANSWERABLE_CATEGORIES:
            return self.status in ANSWERS
        return self.status == e.expected_status.value and self.refusal == (
            e.expected_refusal.value if e.expected_refusal else None
        )

    @property
    def docs_ok(self) -> bool:
        """Answerable: every expected document is cited (and only filtered ones)."""
        e = self.entry
        if e.category not in ANSWERABLE_CATEGORIES:
            return not self.cited_docs
        cited = set(self.cited_docs)
        if e.doc_filter and not cited <= set(e.doc_filter):
            return False
        return set(e.expected_doc_ids) <= cited

    @property
    def passed(self) -> bool:
        return self.status_ok and self.docs_ok

    def ranked_ids(self) -> list[str]:
        retrieval = self.trace.get("retrieval") or {}
        return [c for c, _ in retrieval.get("ranked", [])]

    def evidence_ids(self) -> list[str]:
        retrieval = self.trace.get("retrieval") or {}
        return [c for c, _ in retrieval.get("evidence", [])]

    def recall_hit(self) -> bool | None:
        """A gold chunk in the top K; None when the question has no gold chunks."""
        if not self.entry.gold_chunk_ids:
            return None
        return any(g in self.ranked_ids()[:K] for g in self.entry.gold_chunk_ids)


def failure_stage(o: Outcome) -> str:
    """Where a failed question went wrong, read from its trace (9.3)."""
    e, t = o.entry, o.trace
    if o.status == ERROR:
        return "llm unavailable"
    if e.category is GoldenCategory.OUT_OF_SCOPE:
        return "scope guard (missed)" if o.status != "out_of_scope" else "scope guard (category)"
    if o.status == "out_of_scope":
        return "scope guard (over-refusal)" if t.get("guard", {}).get("allowed") is False else (
            "scope classifier (over-refusal)"
            if (t.get("classifier") or {}).get("allowed") is False
            else "output guard"
        )  # fmt: skip
    if e.category is GoldenCategory.UNKNOWN_DOC:
        return "analyzer (unknown document not caught)"
    if e.category is GoldenCategory.NOT_IN_CORPUS:
        return "sufficiency (answered from off-topic evidence)"
    # Answerable from here on.
    if (t.get("analysis") or {}).get("status") == "unknown_doc":
        return "analyzer (named document misread)"
    gold = set(e.gold_chunk_ids)
    if o.status == "not_in_corpus":
        sufficiency = t.get("sufficiency") or {}
        if gold and not gold & set(o.ranked_ids()):
            return "retrieval (gold chunk not in pool)"
        if not o.evidence_ids():
            return "retrieval (no evidence selected)"
        if sufficiency and not sufficiency.get("sufficient"):
            return f"sufficiency ({sufficiency.get('reason')})"
        if t.get("generation") in ("none", "failed"):
            return f"generation ({t.get('generation')})"
        return "validator (every claim dropped)"
    # Answered, but an expected document is missing (or a filter was broken).
    missing = set(e.expected_doc_ids) - set(o.cited_docs)
    for doc in sorted(missing):
        doc_gold = {g for g in gold if g.startswith(f"{doc}:")}
        if doc not in {c.split(":")[0] for c in o.evidence_ids()}:
            return f"retrieval (no evidence from {doc})"
        if doc_gold and not doc_gold & set(o.evidence_ids()):
            return f"retrieval (gold chunk of {doc} not in evidence)"
        if any(d["doc_id"] == doc for d in t.get("dropped", [])):
            return f"validator (claims from {doc} dropped)"
        return f"generation ({doc} not cited)"
    return "filter (cited a document outside doc_filter)"


# --- Running ----------------------------------------------------------------------------


class WaitClock:
    """The rate limiter's sleep, timed, so quota waits can be taken out of latency."""

    def __init__(self) -> None:
        self.waited = 0.0

    def sleep(self, seconds: float) -> None:
        self.waited += seconds
        time.sleep(seconds)


def run(
    entries: Sequence[GoldenEntry],
    settings: Settings,
    judge: bool,
    traces: TraceLog,
    cache_dir: Path | None = None,
) -> list[Outcome]:
    from guidance_rag.pipeline import load_pipeline

    clock = WaitClock()
    limits = RateLimits(
        rpm=settings.groq_rpm, rpd=settings.groq_rpd, tpm=settings.groq_tpm, tpd=settings.groq_tpd
    )
    limiter = RateLimiter(limits, sleep=clock.sleep)
    groq_llm = GroqLLM(api_key=settings.groq_api_key.get_secret_value(), limiter=limiter)
    llm = CachedLLM(groq_llm, cache_dir) if cache_dir else CachedLLM(groq_llm)
    pipeline = load_pipeline(settings, limiter=limiter, llm=llm)
    judge_ = Judge(llm, {c.chunk_id: c for c in load_chunks()}) if judge else None
    outcomes: list[Outcome] = []
    try:
        for i, e in enumerate(entries, 1):
            trace = Trace(e.question, e.doc_filter)
            waited, hits, misses = clock.waited, llm.hits, llm.misses
            start = time.perf_counter()
            answer: Answer | None = None
            try:
                answer = pipeline.run(e.question, e.doc_filter, trace)
            except LLMError as exc:
                trace.error = f"{type(exc).__name__}: {exc}"
            latency = time.perf_counter() - start
            trace.latency_ms = round(latency * 1000, 1)
            traces.write(trace)
            o = outcome(e, answer, asdict(trace), latency, clock.waited - waited)
            o.llm_hits, o.llm_misses = llm.hits - hits, llm.misses - misses
            if judge_ is not None and answer is not None and answer.sections:
                o.judged = judge_.judge(e.question, answer)
            outcomes.append(o)
            mark = "ok  " if o.passed else "FAIL"
            print(f"[{i:2}/{len(entries)}] {mark} {e.id} {o.status:<14} {latency:5.1f}s"
                  f"{'' if o.passed else '  ' + failure_stage(o)}", flush=True)  # fmt: skip
    finally:
        pipeline.close()
        llm.close()
    return outcomes


def outcome(
    e: GoldenEntry, answer: Answer | None, trace: dict[str, Any], latency: float, wait: float
) -> Outcome:
    if answer is None:
        return Outcome(e, ERROR, None, [], [], trace, latency, wait, 0, 0)
    doc_of = {c.chunk_id: c.doc_id for c in answer.citations}
    claims = [
        (s.doc_id, [doc_of.get(c, "?") for c in claim.chunk_ids])
        for s in answer.sections
        for claim in s.claims
    ]
    return Outcome(
        e,
        answer.status.value,
        answer.refusal.category.value if answer.refusal else None,
        [s.doc_id for s in answer.sections],
        claims,
        trace,
        latency,
        wait,
        0,
        0,
        answer,
    )


# --- Scoring ----------------------------------------------------------------------------


def rate(hits: int, n: int) -> float | None:
    return hits / n if n else None


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(p) - 1]


def metrics(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    answerable = [o for o in outcomes if o.entry.category in ANSWERABLE_CATEGORIES]
    near = [o for o in outcomes if o.entry.category is GoldenCategory.NEAR_MISS]
    oos = [o for o in outcomes if o.entry.category is GoldenCategory.OUT_OF_SCOPE]
    nic = [
        o
        for o in outcomes
        if o.entry.category in (GoldenCategory.NOT_IN_CORPUS, GoldenCategory.UNKNOWN_DOC)
    ]
    recall = [h for o in answerable if (h := o.recall_hit()) is not None]
    claims = [c for o in outcomes for c in o.claims]
    judged = [j for o in outcomes for j in o.judged if j.verdict is not None]
    live = [o for o in outcomes if o.live]
    net = [o.latency_s - o.wait_s for o in live]
    return {
        "questions": len(outcomes),
        "passed": sum(o.passed for o in outcomes),
        "recall_at_10": rate(sum(recall), len(recall)),
        "recall_n": len(recall),
        "oos_recall": rate(sum(o.status_ok for o in oos), len(oos)),
        "nic_recall": rate(sum(o.status_ok for o in nic), len(nic)),
        "false_refusal": rate(sum(o.status in REFUSALS for o in answerable), len(answerable)),
        "near_miss_false_refusal": rate(sum(o.status in REFUSALS for o in near), len(near)),
        "errors": sum(o.status == ERROR for o in outcomes),
        "claims": len(claims),
        "blend_rate": rate(sum(any(d != s for d in ds) for s, ds in claims), len(claims)) or 0.0,
        "uncited_claims": sum(not ds for _, ds in claims),
        "judged": len(judged),
        "citation_precision": rate(
            sum(j.verdict is Verdict.SUPPORTED for j in judged), len(judged)
        ),
        "verdicts": dict(Counter(j.verdict.value for j in judged if j.verdict)),
        "live": len(live),
        "p50_latency_s": percentile(sorted(net), 50),
        "p95_latency_s": percentile(sorted(net), 95),
        "p50_latency_all_s": percentile(sorted(o.latency_s for o in outcomes), 50),
        "p95_latency_all_s": percentile(sorted(o.latency_s for o in outcomes), 95),
    }


def missed_targets(m: dict[str, Any]) -> list[str]:
    """Targets that were measured and missed (unmeasured ones aren't counted)."""
    return [t.name for key, t in TARGETS.items() if m.get(key) is not None and not t.passes(m[key])]


# --- Report -----------------------------------------------------------------------------


def fmt(value: Any, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.0%}" if pct else f"{value:.2f}"
    return str(value)


PCT = {"oos_recall", "nic_recall", "false_refusal", "near_miss_false_refusal"}


def report(outcomes: Sequence[Outcome], m: dict[str, Any], title: str) -> str:
    lines = [f"# {title}", ""]
    lines += ["| Metric | Result | Target | |", "|---|---|---|---|"]
    for key, t in TARGETS.items():
        value = m.get(key)
        mark = "—" if value is None else ("✅" if t.passes(value) else "❌")
        lines.append(f"| {t.name} | {fmt(value, key in PCT)} | {t.goal} | {mark} |")
    lines += [
        "",
        f"- Questions: {m['questions']}, passed {m['passed']} (status and cited documents right).",
        f"- Recall@10 over {m['recall_n']} answerable questions with gold chunks.",
        f"- False refusals on near misses: {fmt(m['near_miss_false_refusal'], True)}.",
        f"- Errors (pipeline raised): {m['errors']}.",
        f"- Claims rendered: {m['claims']}; judged: {m['judged']} {m['verdicts'] or ''}.",
        f"- Latency over {m['live']} questions answered live (no LLM cache hits), quota waits "
        f"excluded: p50 {fmt(m['p50_latency_s'])} s, p95 {fmt(m['p95_latency_s'])} s. All "
        f"questions as run (cache hits included): p50 {fmt(m['p50_latency_all_s'])} s, "
        f"p95 {fmt(m['p95_latency_all_s'])} s.",
        "",
        "## By category",
        "",
        "| Category | Questions | Status right | Docs right | Passed |",
        "|---|---|---|---|---|",
    ]
    by_cat: dict[str, list[Outcome]] = {}
    for o in outcomes:
        by_cat.setdefault(o.entry.category.value, []).append(o)
    for cat, os_ in by_cat.items():
        lines.append(
            f"| {cat} | {len(os_)} | {sum(o.status_ok for o in os_)} | "
            f"{sum(o.docs_ok for o in os_)} | {sum(o.passed for o in os_)} |"
        )
    failed = [o for o in outcomes if not o.passed]
    lines += ["", "## Failures", ""]
    if not failed:
        lines.append("None.")
    else:
        lines += [
            "| Id | Category | Expected | Got | Cited | Stage | Trace |",
            "|---|---|---|---|---|---|---|",
        ]
        for o in failed:
            e = o.entry
            expected = e.expected_status.value + (
                f"/{e.expected_refusal.value}" if e.expected_refusal else ""
            )
            got = o.status + (f"/{o.refusal}" if o.refusal else "")
            lines.append(
                f"| {e.id} | {e.category.value} | {expected} | {got} | "
                f"{', '.join(o.cited_docs) or '—'} | {failure_stage(o)} | "
                f"`{o.trace.get('trace_id', '')[:12]}` |"
            )
    weak = [
        (o.entry.id, j) for o in outcomes for j in o.judged if j.verdict is not Verdict.SUPPORTED
    ]
    if weak:
        lines += ["", "## Claims the judge didn't mark supported", ""]
        lines += ["| Id | Verdict | Claim | Reason |", "|---|---|---|---|"]
        for qid, j in weak:
            verdict = j.verdict.value if j.verdict else "none"
            lines.append(f"| {qid} | {verdict} | {cell(j.text)} | {cell(j.reason)} |")
    lines += ["", "## All questions", ""]
    lines += [
        "| Id | Split | Category | Got | Cited | Latency (s) | Live |",
        "|---|---|---|---|---|---|---|",
    ]
    for o in outcomes:
        lines.append(
            f"| {o.entry.id} | {'holdout' if o.entry.holdout else 'dev'} | "
            f"{o.entry.category.value} | {o.status}{'' if o.passed else ' ❌'} | "
            f"{', '.join(o.cited_docs) or '—'} | {o.latency_s:.1f} | {'yes' if o.live else ''} |"
        )
    return "\n".join(lines) + "\n"


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--set", type=Path, default=GOLDEN_PATH, help="question file")
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="dev")
    parser.add_argument("--id", action="append", default=[], help="only these question ids")
    parser.add_argument("--judge", action="store_true", help="judge citation precision")
    parser.add_argument("--out", type=Path, help="write the Markdown report here")
    parser.add_argument("--json", type=Path, help="write the metrics as JSON here")
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--judged-out", type=Path, help="write every judged claim (JSONL)")
    parser.add_argument("--check", action="store_true", help="exit 1 if a target is missed")
    parser.add_argument(
        "--no-cache", action="store_true", help="answer live (fresh LLM cache), for latency"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    entries = load_golden(args.set).questions
    if args.split != "all":
        entries = [e for e in entries if e.holdout == (args.split == "holdout")]
    if args.id:
        entries = [e for e in entries if e.id in args.id]
    with tempfile.TemporaryDirectory() as fresh:
        cache_dir = Path(fresh) if args.no_cache else None
        outcomes = run(entries, get_settings(), args.judge, TraceLog(args.traces), cache_dir)
    m = metrics(outcomes)
    title = f"Eval report: {args.set.name}, {args.split} split ({len(entries)} questions)"
    text = report(outcomes, m, title)
    print("\n" + text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(m, indent=2), encoding="utf-8")
    if args.judged_out:
        with args.judged_out.open("w", encoding="utf-8") as f:
            for o in outcomes:
                for j in o.judged:
                    row = {"id": o.entry.id, "question": o.entry.question, **asdict(j)}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
    missed = missed_targets(m)
    if missed:
        print(f"Targets missed: {', '.join(missed)}", file=sys.stderr)
    return 1 if args.check and missed else 0


if __name__ == "__main__":
    sys.exit(main())
