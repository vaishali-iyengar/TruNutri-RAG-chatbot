"""The question-answering pipeline (ARCHITECTURE.md §6.1, §7.1; implementation-plan.md 5.6, 6.7).

    input guard -> classifier -> analyzer -> retriever -> generator -> validator
                -> output guard -> renderer

The input guard runs first, so a refused question never reaches retrieval or an LLM.
The answer step (`RagAnswerer`) returns either a final `Answer` (a not-in-corpus
refusal) or a validated `Draft`; the pipeline then applies the output guard and renders,
so citation numbers only ever point at claims that survive. Every outcome is an
`Answer`, refusals included.

Each run fills a `Trace` (8.3): the pipeline records the guard decisions and the final
status, and `RagAnswerer` the analysis, retrieval, sufficiency verdict, raw LLM JSON and
dropped claims.
"""

import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Protocol

from guidance_rag.config import Settings, get_settings
from guidance_rag.generator import Generator
from guidance_rag.llm import LLM, CachedLLM, GroqLLM, LLMUnavailable
from guidance_rag.models import Answer, AnswerStatus, Chunk, DocAnswer, Refusal
from guidance_rag.query.analyzer import AnalysisStatus, QueryAnalyzer
from guidance_rag.query.retriever import Retriever, load_retriever
from guidance_rag.query.scope_classifier import classifier_from_settings
from guidance_rag.query.scope_guard import GuardResult, ScopeCategory, ScopeGuard, default_guard
from guidance_rag.rate_limit import RateLimiter, limiter_from_settings
from guidance_rag.refusals import not_in_corpus_refusal, scope_refusal, unknown_doc_refusal
from guidance_rag.registry import Registry, load_registry
from guidance_rag.render import render_answer
from guidance_rag.sufficiency import EvidenceChecker, SufficiencyGate
from guidance_rag.tracing import RANKED_KEPT, Trace, active, record, scored, timed
from guidance_rag.validator import DroppedClaim, validate

log = logging.getLogger(__name__)


@dataclass
class Draft:
    """A validated answer, before the output guard and rendering."""

    sections: list[DocAnswer]
    chunks: dict[str, Chunk]  # the evidence, for citations
    doc_order: list[str]  # documents by best rerank score
    docs_searched: list[str]
    status: AnswerStatus = AnswerStatus.ANSWERED
    not_covered: str | None = None
    dropped: list[DroppedClaim] = field(default_factory=list)


class AnswerStep(Protocol):
    """Everything after the input guard: analysis, retrieval, generation, validation."""

    def __call__(self, question: str, doc_filter: Sequence[str] | None) -> "Draft | Answer": ...


class InputClassifier(Protocol):
    """An extra input check that can only add refusals (5.7)."""

    def check(self, question: str) -> GuardResult: ...


def refused(
    status: AnswerStatus, refusal: Refusal, trace_id: str = "", docs_searched: Sequence[str] = ()
) -> Answer:
    return Answer(
        status=status,
        refusal=refusal,
        markdown=refusal.message,
        docs_searched=list(docs_searched),
        trace_id=trace_id,
    )


def out_of_scope(category: ScopeCategory, trace_id: str) -> Answer:
    return refused(AnswerStatus.OUT_OF_SCOPE, scope_refusal(category.refusal), trace_id)


def guard_record(result: GuardResult) -> dict[str, object]:
    return {
        "allowed": result.allowed,
        "category": result.category.value if result.category else None,
        "rule": result.matched_rule,
    }


class RagAnswerer:
    """The answer step (6.7, 7.4): analyzer -> retriever -> sufficiency gate -> generator
    -> validator. NOT_IN_CORPUS when the named document isn't in the corpus, the gate
    finds the evidence insufficient, or no claim survives generation and validation."""

    def __init__(
        self,
        analyzer: QueryAnalyzer,
        retriever: Retriever,
        generator: Generator,
        registry: Registry,
        gate: SufficiencyGate | None = None,
    ) -> None:
        self.analyzer, self.retriever, self.generator = analyzer, retriever, generator
        self.gate = gate
        self.documents = {d.doc_id: d for d in registry.included}

    def _not_in_corpus(self, searched: Sequence[str]) -> Answer:
        docs = [self.documents[d] for d in searched if d in self.documents]
        return refused(
            AnswerStatus.NOT_IN_CORPUS, not_in_corpus_refusal(docs), docs_searched=list(searched)
        )

    def __call__(self, question: str, doc_filter: Sequence[str] | None = None) -> Draft | Answer:
        with timed("retrieval"):
            analysis = self.analyzer.analyze(question, doc_filter)
        record(
            analysis={
                "status": analysis.status.value,
                "query": analysis.query,
                "doc_ids": analysis.doc_ids,
                "sub_queries": analysis.sub_queries,
                "unknown_sources": analysis.unknown_sources,
            }
        )
        if analysis.status is AnalysisStatus.UNKNOWN_DOC:
            refusal = unknown_doc_refusal(analysis.unknown_sources, list(self.documents.values()))
            return refused(AnswerStatus.NOT_IN_CORPUS, refusal)

        with timed("retrieval"):
            evidence = self.retriever.retrieve(
                analysis.query, analysis.doc_ids, analysis.sub_queries
            )
        searched = evidence.docs_searched
        record(
            retrieval={
                "docs_searched": searched,
                "best_score": evidence.best_score,
                "evidence": scored(
                    [(sc.chunk.chunk_id, sc.score) for d in evidence.documents for sc in d.chunks]
                ),
                "ranked": scored(evidence.ranked[:RANKED_KEPT]),
                "timings_ms": evidence.timings_ms,
            }
        )
        if not evidence.documents:
            return self._not_in_corpus(searched)

        # Sufficiency gate (7.1-7.2): score check, then the LLM evidence check.
        gap: str | None = None
        if self.gate is not None:
            with timed("sufficiency"):
                sufficiency = self.gate.assess(question, evidence)
            verdict = sufficiency.verdict
            record(
                sufficiency={
                    "sufficient": sufficiency.sufficient,
                    "reason": sufficiency.reason,
                    "best_score": sufficiency.best_score,
                    "tau_answer": self.gate.tau_answer,
                    "verdict": verdict.verdict.value if verdict else None,
                    "supporting": verdict.supporting if verdict else [],
                    "not_covered": sufficiency.not_covered,
                    "notes": sufficiency.notes,
                }
            )
            if not sufficiency.sufficient:
                log.info(
                    "not in corpus (%s, best score %s)", sufficiency.reason, sufficiency.best_score
                )
                return self._not_in_corpus(searched)
            gap = sufficiency.not_covered

        # The generator sees the user's question as asked, document names included.
        # LLMUnavailable propagates: an outage is an error, not a refusal (9.5).
        try:
            with timed("generation"):
                generation = self.generator.generate(question, evidence)
        except LLMUnavailable:
            record(generation="unavailable")
            raise
        if generation is None:
            record(generation="failed")
        else:
            record(generation=generation.status, llm_raw=generation.raw)
        if generation is None or generation.status == "none" or not generation.sections:
            return self._not_in_corpus(searched)

        with timed("validation"):
            validation = validate(generation.sections, evidence)
        record(dropped=[asdict(d) for d in validation.dropped])
        for d in validation.dropped:
            log.info("validator dropped a claim (%s, %s): %r", d.reason, d.doc_id, d.text)
        if not validation.sections:
            return self._not_in_corpus(searched)

        # Partial when the generator says so, or the evidence check found a gap.
        partial = generation.status == "partial" or gap is not None
        return Draft(
            sections=validation.sections,
            chunks={sc.chunk.chunk_id: sc.chunk for d in evidence.documents for sc in d.chunks},
            doc_order=[d.doc_id for d in evidence.documents],
            docs_searched=searched,
            status=AnswerStatus.PARTIAL if partial else AnswerStatus.ANSWERED,
            not_covered=(generation.not_covered or gap) if partial else None,
            dropped=validation.dropped,
        )

    def close(self) -> None:
        self.retriever.close()


class Pipeline:
    def __init__(
        self,
        answer: AnswerStep,
        guard: ScopeGuard | None = None,
        classifier: InputClassifier | None = None,
    ) -> None:
        self.answer = answer
        self.guard = guard or default_guard()
        self.classifier = classifier

    def run(
        self, question: str, doc_filter: Sequence[str] | None = None, trace: Trace | None = None
    ) -> Answer:
        """Answer `question`. Pass a `trace` to keep the record of the run (8.3); its
        trace_id becomes the answer's."""
        trace = trace or Trace(question, list(doc_filter) if doc_filter is not None else None)
        with active(trace):
            answer = self._run(question, doc_filter, trace.trace_id)
            record(
                status=answer.status.value,
                refusal=answer.refusal.category.value if answer.refusal else None,
                citations=[c.chunk_id for c in answer.citations],
            )
        return answer

    def _run(self, question: str, doc_filter: Sequence[str] | None, trace_id: str) -> Answer:
        with timed("guard"):
            verdict = self.guard.check_input(question)
        record(guard=guard_record(verdict))
        if not verdict.allowed and verdict.category is not None:
            log.info(
                "refused by rule %s (%s) [%s]", verdict.matched_rule, verdict.category, trace_id
            )
            return out_of_scope(verdict.category, trace_id)

        if self.classifier is not None:
            with timed("classifier"):
                extra = self.classifier.check(question)
            record(classifier=guard_record(extra))
            if not extra.allowed and extra.category is not None:
                return out_of_scope(extra.category, trace_id)

        result = self.answer(question, doc_filter)
        if isinstance(result, Answer):
            return result.model_copy(update={"trace_id": trace_id})

        with timed("output"):
            cleaned = self.guard.check_output(result.sections)
        record(output_removed=[asdict(r) for r in cleaned.removed])
        for r in cleaned.removed:
            log.warning("output guard removed a claim (%s, %s): %r", r.rule, r.doc_id, r.text)
        if cleaned.refused and cleaned.category is not None:
            return out_of_scope(cleaned.category, trace_id)

        with timed("output"):
            return render_answer(
                cleaned.sections,
                result.chunks,
                trace_id,
                doc_order=result.doc_order,
                docs_searched=result.docs_searched,
                status=result.status,
                not_covered=result.not_covered,
            )

    def close(self) -> None:
        close = getattr(self.answer, "close", None)
        if callable(close):
            close()


def load_pipeline(
    settings: Settings | None = None, limiter: RateLimiter | None = None, llm: LLM | None = None
) -> Pipeline:
    """The full pipeline over the built index, with Groq for generation (needs GROQ_API_KEY
    and `uv sync --extra embed`). LLM replies are cached in .cache/llm/. The eval passes
    its own `limiter` and `llm` to count quota waits and cache hits."""
    settings = settings or get_settings()
    registry = load_registry(settings.registry_path)
    limiter = limiter or limiter_from_settings(settings)
    llm = llm or CachedLLM(
        GroqLLM(api_key=settings.groq_api_key.get_secret_value(), limiter=limiter)
    )
    answerer = RagAnswerer(
        QueryAnalyzer(registry),
        load_retriever(index_dir=settings.index_path, qdrant_url=settings.qdrant_url),
        Generator(llm, settings.generator_model),
        registry,
        SufficiencyGate(settings.tau_answer, EvidenceChecker(llm, settings.evidence_check_model)),
    )
    return Pipeline(answerer, classifier=classifier_from_settings(settings, limiter))
