"""Retrieval eval on the golden set (implementation-plan.md, 4.8).

Runs the query analyzer and the retriever on every golden question and reports, for
the answerable ones with gold chunks:

- Recall@5 / Recall@10: a gold chunk is in the top k of the ranking (rerank order,
  or pool order with --no-rerank).
- MRR of the first gold chunk.
- Pool recall: a gold chunk reached the reranker. Evidence recall: a gold chunk is in
  the selected evidence.
- Cross-document coverage: every expected document has a gold chunk in the evidence.

    .venv/bin/python -m eval.run_retrieval_eval                # hybrid + per-doc + rerank
    .venv/bin/python -m eval.run_retrieval_eval --dense-only   # or --bm25-only
    .venv/bin/python -m eval.run_retrieval_eval --no-rerank --no-per-doc
    .venv/bin/python -m eval.run_retrieval_eval --compare --out eval/results/retrieval.md

Needs the built index and the `embed` extra (uv sync --extra embed).
"""

import argparse
import logging
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from eval.golden import ANSWERABLE_CATEGORIES, GoldenCategory, GoldenEntry, load_golden
from guidance_rag.config import RetrievalConfig
from guidance_rag.ingest.embed import Embedder, SentenceTransformerEmbedder, Vectors
from guidance_rag.models import Chunk, Evidence, ScoredChunk
from guidance_rag.query.analyzer import AnalysisStatus, QueryAnalyzer
from guidance_rag.query.rerank import CrossEncoderReranker, Reranker
from guidance_rag.query.retriever import Retriever, select
from guidance_rag.store import DEFAULT_INDEX_DIR, BM25Index, VectorStore

TAU_SWEEP = [0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]

# (label, config changes); the first one is the default pipeline.
VARIANTS: list[tuple[str, dict[str, bool | int]]] = [
    ("hybrid + per-doc + rerank", {}),
    ("hybrid + rerank, no per-doc", {"per_doc_k": 0}),
    ("hybrid + per-doc, no rerank", {"rerank": False}),
    ("hybrid, no per-doc, no rerank", {"per_doc_k": 0, "rerank": False}),
    ("dense + per-doc + rerank", {"bm25": False}),
    ("dense, no per-doc, no rerank", {"bm25": False, "per_doc_k": 0, "rerank": False}),
    ("BM25 + per-doc + rerank", {"dense": False}),
    ("BM25, no per-doc, no rerank", {"dense": False, "per_doc_k": 0, "rerank": False}),
]


class CachedQueries:
    """Embeds each query once across variants."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder, self._cache = embedder, dict[str, Vectors]()

    @property
    def name(self) -> str:
        return self.embedder.name

    @property
    def dim(self) -> int:
        return self.embedder.dim

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        return self.embedder.embed_documents(texts)

    def embed_query(self, text: str) -> Vectors:
        if text not in self._cache:
            self._cache[text] = self.embedder.embed_query(text)
        return self._cache[text]


class CachedReranker:
    """Scores each (query, text) pair once across variants."""

    def __init__(self, reranker: Reranker) -> None:
        self.reranker, self._cache = reranker, dict[tuple[str, str], float]()

    @property
    def name(self) -> str:
        return self.reranker.name

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        missing = list(dict.fromkeys(t for t in texts if (query, t) not in self._cache))
        for text, s in zip(missing, self.reranker.score(query, missing), strict=True):
            self._cache[(query, text)] = s
        return [self._cache[(query, t)] for t in texts]


def covers(q: GoldenEntry, chunk_ids: Sequence[str]) -> bool:
    """Every expected document has one of its gold chunks among `chunk_ids`."""
    return all(
        any(g in chunk_ids for g in q.gold_chunk_ids if g.startswith(f"{d}:"))
        for d in q.expected_doc_ids
    )


@dataclass
class Result:
    q: GoldenEntry
    status: AnalysisStatus
    doc_ids: list[str] | None
    evidence: Evidence | None

    def rank(self) -> int | None:
        """1-based rank of the best gold chunk in the ranking."""
        if not self.evidence:
            return None
        ids = [c for c, _ in self.evidence.ranked]
        ranks = [ids.index(g) + 1 for g in self.q.gold_chunk_ids if g in ids]
        return min(ranks) if ranks else None

    def gold_score(self) -> float | None:
        """Best score of a gold chunk in the ranking."""
        if not self.evidence:
            return None
        found = [s for c, s in self.evidence.ranked if c in self.q.gold_chunk_ids]
        return max(found) if found else None

    def in_pool(self) -> bool:
        ev = self.evidence
        return ev is not None and any(g in ev.pool for g in self.q.gold_chunk_ids)

    def in_evidence(self) -> bool:
        ev = self.evidence
        return ev is not None and any(g in ev.chunk_ids for g in self.q.gold_chunk_ids)

    def docs_present(self) -> bool:
        return docs_present(self.q, self.evidence.chunk_ids if self.evidence else [])

    def docs_covered(self) -> bool:
        return covers(self.q, self.evidence.chunk_ids if self.evidence else [])


@dataclass
class Report:
    label: str
    results: list[Result] = field(default_factory=list)

    @property
    def scored(self) -> list[Result]:
        return [r for r in self.results if r.q.gold_chunk_ids]

    def metrics(self) -> dict[str, str]:
        rs = self.scored
        n = len(rs)
        ranks = [r.rank() for r in rs]
        cross = [r for r in rs if r.q.category is GoldenCategory.CROSS_DOC]
        totals = [sum(r.evidence.timings_ms.values()) for r in rs if r.evidence]
        return {
            "R@5": f"{sum(1 for k in ranks if k and k <= 5) / n:.2f}",
            "R@10": f"{sum(1 for k in ranks if k and k <= 10) / n:.2f}",
            "MRR": f"{sum(1 / k for k in ranks if k) / n:.2f}",
            "pool": f"{sum(r.in_pool() for r in rs)}/{n}",
            "evidence": f"{sum(r.in_evidence() for r in rs)}/{n}",
            "cross-doc gold": f"{sum(r.docs_covered() for r in cross)}/{len(cross)}",
            "cross-doc docs": f"{sum(r.docs_present() for r in cross)}/{len(cross)}",
            "p50 ms": f"{statistics.median(totals):.0f}" if totals else "-",
        }


def run(
    label: str,
    retriever: Retriever,
    analyzer: QueryAnalyzer,
    questions: Sequence[GoldenEntry],
) -> Report:
    report = Report(label)
    for q in questions:
        analysis = analyzer.analyze(q.question, q.doc_filter)
        evidence = None
        if analysis.status is AnalysisStatus.OK:
            evidence = retriever.retrieve(analysis.query, analysis.doc_ids, analysis.sub_queries)
        report.results.append(Result(q, analysis.status, analysis.doc_ids, evidence))
    return report


def table(reports: Sequence[Report]) -> str:
    keys = list(reports[0].metrics())
    lines = [
        "| Variant | " + " | ".join(keys) + " |",
        "|---|" + "---:|" * len(keys),
    ]
    for rep in reports:
        lines.append(f"| {rep.label} | " + " | ".join(rep.metrics().values()) + " |")
    return "\n".join(lines)


def misses(report: Report) -> str:
    lines = [
        "| Question | Category | Filter | Gold rank | Gold score | In pool | In evidence |",
        "|---|---|---|---:|---:|:-:|:-:|",
    ]
    for r in report.scored:
        rank = r.rank()
        if rank is not None and rank <= 10 and r.in_evidence() and r.docs_covered():
            continue
        lines.append(
            f"| {r.q.id} {r.q.question} | {r.q.category} | {', '.join(r.doc_ids or ['all'])} "
            f"| {rank or '-'} | {_fmt(r.gold_score())} | {'yes' if r.in_pool() else 'no'} "
            f"| {'yes' if r.in_evidence() else 'no'} |"
        )
    return "\n".join(lines) if len(lines) > 2 else "None."


def _fmt(score: float | None) -> str:
    return "-" if score is None else f"{score:.3f}"


def docs_present(q: GoldenEntry, chunk_ids: Sequence[str]) -> bool:
    """Every expected document has some chunk among `chunk_ids` (the exit criterion)."""
    return all(any(c.startswith(f"{d}:") for c in chunk_ids) for d in q.expected_doc_ids)


def sweep(report: Report, chunks: Mapping[str, Chunk], config: RetrievalConfig) -> str:
    """Evidence selection redone at several thresholds from the saved scores: tau_doc
    alone (tau_doc_extra equal), then tau_doc_extra below the configured tau_doc."""
    lines = [
        "| tau_doc | tau_doc_extra | Evidence recall | Cross-doc gold | Cross-doc docs "
        "| Not-in-corpus with evidence | Other answerable with an unexpected doc "
        "| Mean chunks | Mean docs |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    answerable = report.scored
    cross = [r for r in answerable if r.q.category is GoldenCategory.CROSS_DOC]
    single = [r for r in answerable if r.q.category is not GoldenCategory.CROSS_DOC]
    negatives = [
        r for r in report.results if r.q.category is GoldenCategory.NOT_IN_CORPUS and r.evidence
    ]
    grid = [(t, t) for t in TAU_SWEEP]
    grid += [(config.tau_doc, e) for e in TAU_SWEEP if e < config.tau_doc]
    for tau, extra in grid:
        picked: dict[str, list[str]] = {}
        sizes: list[tuple[int, int]] = []
        for r in report.results:
            if r.evidence is None:
                continue
            ranked = [ScoredChunk(chunk=chunks[c], score=s) for c, s in r.evidence.ranked]
            docs = select(ranked, config, tau, extra)
            picked[r.q.id] = [sc.chunk.chunk_id for d in docs for sc in d.chunks]
            if r.q.gold_chunk_ids:
                sizes.append((len(picked[r.q.id]), len(docs)))

        def got(r: Result, picked: dict[str, list[str]] = picked) -> list[str]:
            return picked.get(r.q.id, [])

        recall = sum(any(g in got(r) for g in r.q.gold_chunk_ids) for r in answerable)
        gold = sum(covers(r.q, got(r)) for r in cross)
        present = sum(docs_present(r.q, got(r)) for r in cross)
        with_evidence = sum(bool(got(r)) for r in negatives)
        noisy = sum(
            any(c.split(":")[0] not in r.q.expected_doc_ids for c in got(r)) for r in single
        )
        mean_chunks = statistics.mean(n for n, _ in sizes)
        mean_docs = statistics.mean(d for _, d in sizes)
        lines.append(
            f"| {tau} | {extra} | {recall}/{len(answerable)} | {gold}/{len(cross)} "
            f"| {present}/{len(cross)} | {with_evidence}/{len(negatives)} "
            f"| {noisy}/{len(single)} | {mean_chunks:.1f} | {mean_docs:.1f} |"
        )
    return "\n".join(lines)


def scores(report: Report) -> str:
    """Best rerank score per golden question, by category (input for Phase 7)."""
    lines = ["| Category | Question | Best score | Evidence docs |", "|---|---|---:|---|"]
    order = list(GoldenCategory)
    for r in sorted(
        report.results,
        key=lambda r: (
            order.index(r.q.category),
            -(r.evidence.best_score or 0) if r.evidence else 0,
        ),
    ):
        if r.evidence is None:
            best, docs = r.status.value.upper(), "-"
        else:
            best = f"{r.evidence.best_score:.3f}" if r.evidence.best_score is not None else "-"
            docs = ", ".join(d.doc_id for d in r.evidence.documents) or "none"
        lines.append(f"| {r.q.category} | {r.q.id} {r.q.question} | {best} | {docs} |")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dense-only", action="store_true")
    parser.add_argument("--bm25-only", action="store_true")
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--no-per-doc", action="store_true")
    parser.add_argument("--compare", action="store_true", help="run every variant")
    parser.add_argument("--reranker", help="cross-encoder model (default: RetrievalConfig)")
    parser.add_argument("--out", type=Path, help="also write the report to this Markdown file")
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    if args.compare:
        variants = VARIANTS
    else:
        changes: dict[str, bool | int] = {}
        if args.dense_only:
            changes["bm25"] = False
        if args.bm25_only:
            changes["dense"] = False
        if args.no_rerank:
            changes["rerank"] = False
        if args.no_per_doc:
            changes["per_doc_k"] = 0
        variants = [(", ".join(f"{k}={v}" for k, v in changes.items()) or "default", changes)]
    base = RetrievalConfig(**({"reranker_model": args.reranker} if args.reranker else {}))

    golden = load_golden()
    questions = golden.questions
    store = VectorStore(path=args.index_dir)
    if not store.exists():
        print("No index: run `python -m guidance_rag.ingest index` first.", file=sys.stderr)
        return 1
    bm25 = BM25Index.from_dir()
    bm25_chunks = {c.chunk_id: c for c in bm25.chunks}
    embedder = CachedQueries(SentenceTransformerEmbedder())
    needs_rerank = any(changes.get("rerank", True) for _, changes in variants)
    reranker = CachedReranker(CrossEncoderReranker(base)) if needs_rerank else None
    analyzer = QueryAnalyzer()

    reports = []
    try:
        for label, changes in variants:
            config = base.model_copy(update=changes)
            retriever = Retriever(
                store, bm25, embedder, reranker if config.rerank else None, config
            )
            reports.append(run(label, retriever, analyzer, questions))
            print(f"ran: {label}", file=sys.stderr)
    finally:
        store.close()

    answerable = sum(
        1 for q in questions if q.category in ANSWERABLE_CATEGORIES and q.gold_chunk_ids
    )
    text = "\n\n".join(
        [
            "# Retrieval eval",
            f"Golden set v{golden.version}: {answerable} answerable questions with gold chunks. "
            f"Reranker: `{base.reranker_model}`. "
            "Latency (p50 ms) is embed + search + rerank per question; with --compare only the "
            "first variant's timings are cold, later variants reuse cached model outputs.",
            "## Metrics",
            table(reports),
            f"## Misses: {reports[0].label}",
            "Questions whose best gold chunk is outside the top 10, missing from the evidence, "
            "or (cross-document) missing a document.",
            misses(reports[0]),
            f"## Threshold sweep: {reports[0].label}",
            "Evidence selection recomputed from the saved scores at each threshold "
            "(meaningful only with rerank on).",
            sweep(reports[0], bm25_chunks, base),
            f"## Best rerank score per question: {reports[0].label}",
            scores(reports[0]),
        ]
    )
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
