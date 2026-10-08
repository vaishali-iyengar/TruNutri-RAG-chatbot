"""LLM client for JSON answers (implementation-plan.md, 6.1).

`LLM` is the interface the generator uses; `GroqLLM` runs it on Groq with strict
structured output, a timeout, and retries with backoff (the Groq SDK retries
connection errors, 408, 409, 429 and 5xx). Given a `RateLimiter`, it keeps every
request inside the account's quotas (rate_limit.py). `CachedLLM` stores complete responses on
disk, keyed by a hash of the request, so tests and evals repeat without new API calls.
Tests use a fake that returns queued replies.

`time_limit()` sets a deadline for everything inside it (9.5): `GroqLLM` shortens each
call's timeout to the time left, and won't wait on the rate limiter past it, so a request
fails fast with `LLMError` instead of hanging on a quota wait or a slow API.
"""

import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import groq

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.rate_limit import (
    RateLimiter,
    RateLimitExceeded,
    daily_quota_reset,
    estimate_prompt_tokens,
)

log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache" / "llm"

ReasoningEffort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class JsonRequest:
    model: str
    system: str
    user: str
    schema: dict[str, Any]  # JSON schema; strict mode (all properties required, no extras)
    schema_name: str
    max_tokens: int = 4096  # includes the model's reasoning tokens
    temperature: float = 0.0
    reasoning_effort: ReasoningEffort = "medium"

    def key(self) -> str:
        """A stable hash of everything that shapes the reply."""
        data = json.dumps(self.__dict__, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    finish_reason: str  # "stop" when complete; "length" when cut off by max_tokens

    @property
    def complete(self) -> bool:
        return self.finish_reason == "stop" and bool(self.content)


class LLMError(RuntimeError):
    """The LLM could not be reached or returned an error."""


class LLMUnavailable(LLMError):
    """The LLM service gave no reply at all: unreachable, timed out or out of quota.
    Raised by the generator so the API reports an error instead of an answer (9.5)."""


# --- Deadline (9.5) ----------------------------------------------------------------------

_deadline: ContextVar[float | None] = ContextVar("llm_deadline", default=None)


@contextmanager
def time_limit(seconds: float) -> Iterator[None]:
    """LLM calls inside this block must finish within `seconds` (monotonic clock)."""
    end = time.monotonic() + seconds
    outer = _deadline.get()
    token = _deadline.set(end if outer is None else min(end, outer))
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining() -> float | None:
    """Seconds left before the current deadline; None when there is none."""
    end = _deadline.get()
    return None if end is None else end - time.monotonic()


def call_timeout(default: float) -> float | groq.NotGiven:
    """The `timeout` for a Groq call: no longer than the time left; NOT_GIVEN (the
    client's own timeout) when there is no deadline. None would mean "no timeout"."""
    left = remaining()
    if left is None:
        return groq.NOT_GIVEN
    if left <= 0:
        raise LLMError("time limit reached")
    return min(default, left)


class LLM(Protocol):
    def complete_json(self, request: JsonRequest) -> LLMResponse: ...


class GroqLLM:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        client: Any | None = None,  # a groq.Groq, or a test double
        limiter: RateLimiter | None = None,
    ) -> None:
        self.client = client or groq.Groq(api_key=api_key, timeout=timeout, max_retries=max_retries)
        self.limiter = limiter
        self.timeout = timeout

    def complete_json(self, request: JsonRequest) -> LLMResponse:
        limiter, max_tokens, ticket = self.limiter, request.max_tokens, None
        if limiter is not None:
            schema = json.dumps(request.schema)  # Groq adds the schema to the prompt
            prompt = estimate_prompt_tokens(request.system, request.user, schema)
            try:
                max_tokens = limiter.fit(prompt, request.max_tokens)
                ticket = limiter.acquire(request.model, prompt + max_tokens, max_wait=remaining())
            except RateLimitExceeded as exc:
                raise LLMError(str(exc)) from exc
        timeout = call_timeout(self.timeout)
        try:
            response = self.client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "strict": True,
                        "schema": request.schema,
                    },
                },
                temperature=request.temperature,
                reasoning_effort=request.reasoning_effort,
                include_reasoning=False,
                max_completion_tokens=max_tokens,
                timeout=timeout,
            )
        except groq.APIError as exc:
            reset = daily_quota_reset(str(exc)) if isinstance(exc, groq.RateLimitError) else None
            if reset is not None and limiter is not None:
                limiter.block(request.model, reset)
            raise LLMError(str(exc)) from exc
        usage = getattr(response, "usage", None)
        if limiter is not None and ticket is not None and usage is not None:
            limiter.settle(ticket, usage.total_tokens)
        choice = response.choices[0]
        return LLMResponse(choice.message.content, str(choice.finish_reason))


class CachedLLM:
    """Wraps an LLM with an on-disk cache of complete responses (not cut-off ones)."""

    def __init__(self, llm: LLM, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self.llm = llm
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(cache_dir / "responses.sqlite", check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, content TEXT, finish TEXT)"
        )
        self.hits = 0
        self.misses = 0

    def complete_json(self, request: JsonRequest) -> LLMResponse:
        key = request.key()
        row = self._db.execute(
            "SELECT content, finish FROM responses WHERE key = ?", (key,)
        ).fetchone()
        if row:
            self.hits += 1
            return LLMResponse(row[0], row[1])
        self.misses += 1
        response = self.llm.complete_json(request)
        if response.complete:
            self._db.execute(
                "INSERT OR REPLACE INTO responses VALUES (?, ?, ?)",
                (key, response.content, response.finish_reason),
            )
            self._db.commit()
        return response

    def close(self) -> None:
        self._db.close()
