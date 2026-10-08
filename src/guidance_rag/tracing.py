"""Request tracing (implementation-plan.md, 8.3; ARCHITECTURE.md §11.3).

Each question gets a `Trace` with a `trace_id`, which the API returns. The pipeline
fills it in as the question moves through: guard decision and matched rule, doc filter,
analysis, retrieved chunk IDs with scores, sufficiency verdict, the raw LLM JSON,
dropped claims and the final status. `TraceLog` appends each finished trace to a JSONL
file, one line per request, so every refusal and every citation can be explained later.

Components deep in the pipeline record through `record()`, which writes to the trace of
the current request (a context variable) and does nothing outside one, so they need no
extra parameter and work unchanged in tests and scripts.
"""

import json
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from guidance_rag.config import PROJECT_ROOT

DEFAULT_TRACE_LOG = PROJECT_ROOT / "logs" / "traces.jsonl"
RANKED_KEPT = 20  # pool chunks kept in the trace, best first (the evidence is kept whole)


@dataclass
class Trace:
    question: str
    doc_filter: list[str] | None = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    time: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    guard: dict[str, Any] | None = None  # input guard: allowed, category, rule
    classifier: dict[str, Any] | None = None  # the optional LLM classifier (5.7)
    analysis: dict[str, Any] | None = None  # analyzer: status, search query, doc_ids
    retrieval: dict[str, Any] | None = None  # docs searched, evidence and pool scores
    sufficiency: dict[str, Any] | None = None  # score check and evidence-check verdict
    llm_raw: str | None = None  # the generator's JSON as returned
    generation: str | None = None  # answered | partial | none | failed
    dropped: list[dict[str, Any]] = field(default_factory=list)  # by the validator
    output_removed: list[dict[str, Any]] = field(default_factory=list)  # by the output guard
    status: str | None = None
    refusal: str | None = None
    citations: list[str] = field(default_factory=list)  # cited chunk_ids, in number order
    latency_ms: float | None = None
    # Milliseconds per stage: guard, classifier, retrieval (analyzer included),
    # sufficiency, generation, validation, output (output guard and rendering).
    timings_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


_current: ContextVar[Trace | None] = ContextVar("trace", default=None)


@contextmanager
def active(trace: Trace) -> Iterator[Trace]:
    """Make `trace` the one `record()` writes to, for the duration of the block."""
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)


def current() -> Trace | None:
    return _current.get()


def record(**fields: Any) -> None:
    """Set fields on the current trace; a no-op when no trace is active."""
    trace = _current.get()
    if trace is None:
        return
    for name, value in fields.items():
        if not hasattr(trace, name):
            raise AttributeError(f"Trace has no field {name!r}")
        setattr(trace, name, value)


@contextmanager
def timed(stage: str) -> Iterator[None]:
    """Add the block's duration to the current trace's `timings_ms[stage]`."""
    start = time.perf_counter()
    try:
        yield
    finally:
        trace = _current.get()
        if trace is not None:
            elapsed = (time.perf_counter() - start) * 1000
            trace.timings_ms[stage] = round(trace.timings_ms.get(stage, 0.0) + elapsed, 1)


def scored(pairs: Sequence[tuple[str, float]]) -> list[list[Any]]:
    """(chunk_id, score) pairs as short JSON lists, scores rounded."""
    return [[chunk_id, round(score, 4)] for chunk_id, score in pairs]


class TraceLog:
    """Appends traces to a JSONL file; safe to share between request threads."""

    def __init__(self, path: Path | None = DEFAULT_TRACE_LOG) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, trace: Trace) -> None:
        if self.path is None:
            return
        line = trace.to_json() + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
