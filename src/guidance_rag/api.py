"""HTTP API and chat page (implementation-plan.md, 8.1-8.3; ARCHITECTURE.md §10).

    POST /chat        {"question": "...", "doc_filter": ["doc-id", ...]}  -> the §10 answer
    GET  /documents   the included registry entries (for the "search only in" picker)
    GET  /health      whether the pipeline is loaded
    GET  /            the chat page (ui/index.html)

Run with `uvicorn guidance_rag.api:app` (or `make api`). The pipeline (index, embedding
and rerank models, registry, LLM clients) is loaded once at startup. If that fails, for
example because nothing is indexed yet, the API still starts: /health says why, /chat
answers 503, and each /health or /chat call tries loading again, so `make ingest` after
`docker compose up` gives a working chat without a restart.

Questions are answered one at a time: the local Qdrant store and the models aren't
shared across threads, and the Groq quota allows only a few answers a minute anyway.
Every /chat call appends one trace line to logs/traces.jsonl (8.3).

Failure handling (9.5): each client IP gets `rate_per_minute` /chat calls a minute (more
get 429 with Retry-After). Each question must finish within `timeout_s`, waiting in line
included. If the answer model is unreachable, times out or is out of quota, /chat
returns 503 with the trace_id: an error, never an ungrounded answer and never a
"not in the documents" refusal that would misstate what the corpus holds.
"""

import logging
import math
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from guidance_rag.config import ConfigError, Settings, get_settings
from guidance_rag.llm import LLMError, time_limit
from guidance_rag.models import Answer
from guidance_rag.registry import Registry, load_registry
from guidance_rag.render import api_response
from guidance_rag.tracing import Trace, TraceLog

log = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 1_000
UI_PAGE = Path(__file__).parent / "ui" / "index.html"


@dataclass(frozen=True)
class ChatLimits:
    timeout_s: float = 60.0
    rate_per_minute: int = 20

    @classmethod
    def from_settings(cls, settings: Settings) -> "ChatLimits":
        return cls(settings.chat_timeout_s, settings.chat_rate_per_minute)


class ClientRateLimiter:
    """A sliding one-minute window of /chat calls per client."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self.clock = clock
        self._calls: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str) -> float:
        """Record a call; returns 0 if allowed, else the seconds until one is."""
        now = self.clock()
        with self._lock:
            calls = self._calls.setdefault(client, deque())
            while calls and calls[0] <= now - 60:
                calls.popleft()
            if len(calls) >= self.per_minute:
                return calls[0] + 60 - now
            calls.append(now)
            return 0.0


class ChatPipeline(Protocol):
    def run(
        self, question: str, doc_filter: list[str] | None = None, trace: Trace | None = None
    ) -> Answer: ...

    def close(self) -> None: ...


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=MAX_QUESTION_CHARS)
    doc_filter: list[str] | None = None  # doc_ids; None or [] = search every document

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question is empty")
        return value

    @field_validator("doc_filter")
    @classmethod
    def _no_empty_filter(cls, value: list[str] | None) -> list[str] | None:
        """Repeated doc_ids removed; an empty list means no filter."""
        if not value:
            return None
        return list(dict.fromkeys(d.strip() for d in value))


class PipelineHolder:
    """Loads the pipeline once, retries after a failed load, and runs one question at a time."""

    def __init__(self, factory: Callable[[], ChatPipeline]) -> None:
        self.factory = factory
        self.pipeline: ChatPipeline | None = None
        self.error: str | None = None
        self._lock = threading.Lock()

    def load(self) -> ChatPipeline | None:
        with self._lock:
            return self._load()

    def _load(self) -> ChatPipeline | None:
        if self.pipeline is None:
            start = time.perf_counter()
            try:
                self.pipeline = self.factory()
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                log.error("pipeline not loaded: %s", self.error)
            else:
                self.error = None
                log.info("pipeline loaded in %.1f s", time.perf_counter() - start)
        return self.pipeline

    def run(
        self, question: str, doc_filter: list[str] | None, trace: Trace, deadline: float
    ) -> Answer:
        """Answer by `deadline` (time.monotonic), the wait for the previous question
        included."""
        if not self._lock.acquire(timeout=max(deadline - time.monotonic(), 0)):
            raise HTTPException(503, "The assistant is busy; please try again shortly.")
        try:
            pipeline = self._load()
            if pipeline is None:
                raise HTTPException(503, f"The assistant isn't ready: {self.error}")
            with time_limit(deadline - time.monotonic()):
                return pipeline.run(question, doc_filter, trace)
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            if self.pipeline is not None:
                self.pipeline.close()
                self.pipeline = None


def document_entry(registry: Registry, doc_id: str) -> dict[str, Any]:
    d = registry.get(doc_id)
    return {
        "doc_id": d.doc_id,
        "title": d.title,
        "short_name": d.short_name,
        "publisher": d.publisher,
        "year": d.year,
        "domain": d.domain.value,
        "source_url": str(d.source_url),
        "retrieval_date": d.retrieval_date.isoformat() if d.retrieval_date else None,
    }


def create_app(
    pipeline_factory: Callable[[], ChatPipeline] | None = None,
    registry: Registry | None = None,
    trace_log: TraceLog | None = None,
    limits: ChatLimits | None = None,
) -> FastAPI:
    """The app. Defaults: the full pipeline (`load_pipeline`), the project registry,
    logs/traces.jsonl and limits from settings; tests pass fakes."""
    if pipeline_factory is None:
        from guidance_rag.pipeline import load_pipeline

        pipeline_factory = load_pipeline
    registry = registry or load_registry()
    traces = trace_log or TraceLog()
    holder = PipelineHolder(pipeline_factory)
    doc_ids = [d.doc_id for d in registry.included]
    if limits is None:
        try:
            limits = ChatLimits.from_settings(get_settings())
        except ConfigError:
            limits = ChatLimits()  # the pipeline won't load either; /health will say why
    rate = ClientRateLimiter(limits.rate_per_minute)
    timeout_s = limits.timeout_s

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        holder.load()
        yield
        holder.close()

    app = FastAPI(
        title="Dietary guidance assistant",
        summary="Answers food, nutrition and food-safety questions from official guidance, "
        "with citations.",
        lifespan=lifespan,
    )

    @app.post("/chat")
    def chat(request: ChatRequest, http: Request) -> JSONResponse:
        wait = rate.check(http.client.host if http.client else "unknown")
        if wait > 0:
            raise HTTPException(
                429,
                "Too many questions; please wait a moment.",
                headers={"Retry-After": str(math.ceil(wait))},
            )
        unknown = [d for d in request.doc_filter or [] if d not in doc_ids]
        if unknown:
            raise HTTPException(
                422,
                f"Unknown doc_id(s) in doc_filter: {', '.join(unknown)}. "
                f"Valid doc_ids: {', '.join(doc_ids)}.",
            )
        trace = Trace(request.question, request.doc_filter)
        start = time.perf_counter()
        deadline = time.monotonic() + timeout_s
        try:
            answer = holder.run(request.question, request.doc_filter, trace, deadline)
        except HTTPException as exc:
            trace.error = str(exc.detail)
            raise
        except LLMError as exc:
            log.warning("chat: answer model unavailable [%s]: %s", trace.trace_id, exc)
            trace.error = f"{type(exc).__name__}: {exc}"
            return JSONResponse(
                {"detail": "The answer service is unavailable or timed out; please try again "
                 "in a minute.", "trace_id": trace.trace_id},
                status_code=503,
            )  # fmt: skip
        except Exception as exc:
            log.exception("chat failed [%s]", trace.trace_id)
            trace.error = f"{type(exc).__name__}: {exc}"
            return JSONResponse(
                {"detail": "Something went wrong answering this question.",
                 "trace_id": trace.trace_id},
                status_code=500,
            )  # fmt: skip
        finally:
            trace.latency_ms = round((time.perf_counter() - start) * 1000, 1)
            traces.write(trace)
        return JSONResponse(api_response(answer))

    @app.get("/documents")
    def documents() -> list[dict[str, Any]]:
        return [document_entry(registry, d) for d in doc_ids]

    @app.get("/health")
    def health() -> JSONResponse:
        # Retries a failed load, like /chat, so health turns ok once the index exists.
        ready = holder.load() is not None
        body = {"status": "ok" if ready else "unavailable", "documents": len(doc_ids)}
        if not ready:
            body["error"] = holder.error or "not loaded"
        return JSONResponse(body, status_code=200 if ready else 503)

    @app.get("/", include_in_schema=False)
    def ui() -> FileResponse:
        return FileResponse(UI_PAGE, media_type="text/html")

    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn guidance_rag.api:app` builds the real app on first access, so importing
    # this module (as the tests do) loads no models.
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
