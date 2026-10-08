"""Failure handling (implementation-plan.md, 9.5): time limits, LLM outages, rate limits.

An outage of the answer model must surface as an error, never as an answer and never
as a "not in the documents" refusal.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

from guidance_rag.api import ChatLimits, ClientRateLimiter, create_app
from guidance_rag.generator import Generator
from guidance_rag.llm import GroqLLM, JsonRequest, LLMError, LLMUnavailable, remaining, time_limit
from guidance_rag.pipeline import Pipeline, RagAnswerer
from guidance_rag.query.analyzer import QueryAnalyzer
from guidance_rag.rate_limit import RateLimiter, RateLimitExceeded, RateLimits, daily_quota_reset
from guidance_rag.registry import load_registry
from guidance_rag.tracing import TraceLog
from tests.fakes import DGI_OILS, WHO_FATS, FakeLLM, FakeRetriever, evidence
from tests.test_api import OIL_QUESTION
from tests.test_pipeline import OIL_REPLY
from tests.test_rate_limit import Clock

REGISTRY = load_registry()
EVIDENCE = evidence(DGI_OILS, WHO_FATS)
REQUEST = JsonRequest(
    model="openai/gpt-oss-120b",
    system="system",
    user="user",
    schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    schema_name="test",
)


# --- Generator: outage vs. bad reply --------------------------------------------------


def test_two_service_failures_raise_unavailable() -> None:
    llm = FakeLLM(LLMError("Connection error."), LLMError("Request timed out."))

    with pytest.raises(LLMUnavailable):
        Generator(llm).generate("Which oils?", EVIDENCE)
    assert len(llm.requests) == 2


def test_a_service_failure_then_a_good_reply_answers() -> None:
    llm = FakeLLM(LLMError("Connection error."), OIL_REPLY)

    generation = Generator(llm).generate("Which oils?", EVIDENCE)

    assert generation is not None and generation.status == "answered"


def test_malformed_json_twice_is_still_none_not_an_outage() -> None:
    bad = LLMError("Error code: 400 - {'error': {'code': 'json_validate_failed'}}")
    llm = FakeLLM(bad, bad)

    assert Generator(llm).generate("Which oils?", EVIDENCE) is None


def test_no_retry_once_the_time_limit_has_passed() -> None:
    llm = FakeLLM(LLMError("Request timed out."), OIL_REPLY)

    with time_limit(-1), pytest.raises(LLMUnavailable):
        Generator(llm).generate("Which oils?", EVIDENCE)
    assert len(llm.requests) == 1


# --- Deadline in the Groq client and the rate limiter ------------------------------------


def test_time_limits_nest_to_the_earliest() -> None:
    assert remaining() is None
    with time_limit(30), time_limit(100):
        left = remaining()
        assert left is not None and 29 < left <= 30
    assert remaining() is None


def test_groq_calls_get_a_timeout_within_the_time_limit() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
        usage=None,
    )
    llm = GroqLLM(client=client, timeout=60)

    llm.complete_json(REQUEST)
    first = client.chat.completions.create.call_args.kwargs
    assert first["timeout"] is groq.NOT_GIVEN

    with time_limit(5):
        llm.complete_json(REQUEST)
    second = client.chat.completions.create.call_args.kwargs
    assert 4 < second["timeout"] <= 5

    with time_limit(-1), pytest.raises(LLMError, match="time limit"):
        llm.complete_json(REQUEST)


def test_the_limiter_wont_wait_past_the_time_limit(tmp_path: Path) -> None:
    clock = Clock()
    limiter = RateLimiter(RateLimits(tpm=8_000), tmp_path / "u.sqlite", clock, clock.sleep)
    limiter.acquire("m", 6_000)

    with pytest.raises(RateLimitExceeded, match="time limit"):
        limiter.acquire("m", 6_000, max_wait=10)
    assert clock.slept == []  # failed at once rather than sleeping first

    limiter.acquire("m", 6_000, max_wait=120)  # enough time: waits for the window
    assert clock.slept and clock.slept[0] > 50


# --- API --------------------------------------------------------------------------------


def client_for(llm: FakeLLM, log_path: Path, limits: ChatLimits | None = None) -> TestClient:
    answerer = RagAnswerer(
        QueryAnalyzer(REGISTRY),
        FakeRetriever(EVIDENCE),  # type: ignore[arg-type]
        Generator(llm),
        REGISTRY,
    )
    app = create_app(
        lambda: Pipeline(answerer), REGISTRY, TraceLog(log_path), limits or ChatLimits()
    )
    return TestClient(app)


def test_an_llm_outage_is_a_503_with_the_trace_id(tmp_path: Path) -> None:
    log_path = tmp_path / "traces.jsonl"
    llm = FakeLLM(LLMError("Connection error."), LLMError("Connection error."))
    with client_for(llm, log_path) as c:
        res = c.post("/chat", json={"question": OIL_QUESTION})

    assert res.status_code == 503
    body = res.json()
    assert "unavailable" in body["detail"]
    assert "status" not in body  # no answer, no refusal
    [trace] = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert trace["trace_id"] == body["trace_id"]
    assert trace["generation"] == "unavailable"
    assert trace["error"].startswith("LLMUnavailable")
    assert trace["status"] is None


def test_a_used_up_quota_is_a_503(tmp_path: Path) -> None:
    quota = LLMError("daily request limit reached for openai/gpt-oss-120b (1000/1000)")
    with client_for(FakeLLM(quota, quota), tmp_path / "t.jsonl") as c:
        res = c.post("/chat", json={"question": OIL_QUESTION})

    assert res.status_code == 503


def test_the_request_runs_under_the_time_limit(tmp_path: Path) -> None:
    seen: list[float | None] = []

    class Recording(FakeLLM):
        def complete_json(self, request: JsonRequest) -> Any:
            seen.append(remaining())
            return super().complete_json(request)

    with client_for(Recording(OIL_REPLY), tmp_path / "t.jsonl", ChatLimits(timeout_s=7)) as c:
        assert c.post("/chat", json={"question": OIL_QUESTION}).status_code == 200

    [left] = seen
    assert left is not None and 0 < left <= 7


def test_too_many_questions_from_one_client_get_a_429(tmp_path: Path) -> None:
    llm = FakeLLM(OIL_REPLY, OIL_REPLY)
    with client_for(llm, tmp_path / "t.jsonl", ChatLimits(rate_per_minute=2)) as c:
        assert c.post("/chat", json={"question": OIL_QUESTION}).status_code == 200
        assert c.post("/chat", json={"question": OIL_QUESTION}).status_code == 200
        res = c.post("/chat", json={"question": OIL_QUESTION})

    assert res.status_code == 429
    assert 0 < int(res.headers["Retry-After"]) <= 60
    assert len(llm.requests) == 2  # the third never reached the pipeline


def test_the_client_window_slides() -> None:
    clock = Clock()
    rate = ClientRateLimiter(2, clock)

    assert rate.check("a") == 0 and rate.check("a") == 0
    assert rate.check("a") == pytest.approx(60)
    assert rate.check("b") == 0  # per client
    clock.now += 61
    assert rate.check("a") == 0


# --- Daily quota (found in the 9.1 live runs) --------------------------------------------


def rate_limit_error(message: str) -> groq.RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return groq.RateLimitError(message, response=httpx.Response(429, request=request), body=None)


TPD_429 = (
    "Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` on tokens per day "
    "(TPD): Limit 200000, Used 199611, Requested 2350. Please try again in 14m7.15s."
)


def test_daily_quota_reset_reads_groqs_message() -> None:
    assert daily_quota_reset(TPD_429) == pytest.approx(14 * 60 + 7.15)
    assert daily_quota_reset("... requests per day (RPD) ... try again in 1h2m3s") == 3723
    assert daily_quota_reset("tokens per minute (TPM): try again in 2.5s") is None


def test_after_a_daily_429_the_model_is_blocked_without_calling_groq(tmp_path: Path) -> None:
    clock = Clock()
    limiter = RateLimiter(RateLimits(), tmp_path / "u.sqlite", clock, clock.sleep)
    client = Mock()
    client.chat.completions.create.side_effect = rate_limit_error(TPD_429)
    llm = GroqLLM(client=client, limiter=limiter)

    with pytest.raises(LLMError, match="tokens per day"):
        llm.complete_json(REQUEST)
    with pytest.raises(LLMError, match="daily quota"):
        llm.complete_json(REQUEST)
    assert client.chat.completions.create.call_count == 1  # the second never reached Groq

    clock.now += 15 * 60  # past the reset Groq gave
    client.chat.completions.create.side_effect = None
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
        usage=None,
    )
    assert llm.complete_json(REQUEST).content == "{}"


def test_the_generator_doesnt_retry_a_daily_limit() -> None:
    llm = FakeLLM(LLMError(TPD_429), OIL_REPLY)

    with pytest.raises(LLMUnavailable):
        Generator(llm).generate("Which oils?", EVIDENCE)
    assert len(llm.requests) == 1


def test_stage_timings_are_traced(tmp_path: Path) -> None:
    log_path = tmp_path / "t.jsonl"
    with client_for(FakeLLM(OIL_REPLY), log_path) as c:
        c.post("/chat", json={"question": OIL_QUESTION})

    [trace] = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert set(trace["timings_ms"]) == {
        "guard", "retrieval", "generation", "validation", "output"
    }  # fmt: skip
