"""Client-side Groq rate limits, with a fake clock."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from guidance_rag.llm import GroqLLM, JsonRequest, LLMError
from guidance_rag.query.scope_classifier import ScopeClassifier
from guidance_rag.query.scope_guard import GuardResult
from guidance_rag.rate_limit import (
    RateLimiter,
    RateLimitExceeded,
    RateLimits,
    estimate_prompt_tokens,
)

MODEL = "openai/gpt-oss-120b"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def limiter(tmp_path: Path, clock: Clock, **limits: int) -> RateLimiter:
    return RateLimiter(RateLimits(**limits), tmp_path / "usage.sqlite", clock, clock.sleep)


def test_requests_within_the_limits_do_not_wait(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock)

    for _ in range(3):
        rl.acquire(MODEL, 2_000)

    assert clock.slept == []


def test_the_requests_per_minute_limit_waits_for_the_oldest_request(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, rpm=2)
    rl.acquire(MODEL, 10)
    clock.now += 10
    rl.acquire(MODEL, 10)

    rl.acquire(MODEL, 10)

    assert clock.slept == [pytest.approx(50.05)]  # the first request leaves the window


def test_the_tokens_per_minute_limit_waits_until_enough_tokens_free_up(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, tpm=8_000)
    rl.acquire(MODEL, 3_000)
    clock.now += 5
    rl.acquire(MODEL, 3_000)
    clock.now += 5

    rl.acquire(MODEL, 4_000)  # needs the first reservation to expire, not the second

    assert clock.slept == [pytest.approx(50.05)]


def test_settled_usage_replaces_the_reservation(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, tpm=8_000)
    rl.settle(rl.acquire(MODEL, 7_000), 1_000)

    rl.acquire(MODEL, 7_000)

    assert clock.slept == []


def test_models_have_separate_budgets(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, rpm=1)
    rl.acquire(MODEL, 10)

    rl.acquire("openai/gpt-oss-20b", 10)

    assert clock.slept == []


def test_daily_limits_raise_instead_of_waiting(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, rpd=2, tpd=10_000)
    rl.acquire(MODEL, 10)
    clock.now += 120
    rl.acquire(MODEL, 10)

    with pytest.raises(RateLimitExceeded, match="daily request limit"):
        rl.acquire(MODEL, 10)
    clock.now += 24 * 3600  # a day later both requests have left the window
    rl.acquire(MODEL, 10)


def test_the_daily_token_limit(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, tpd=10_000)
    rl.acquire(MODEL, 6_000)
    clock.now += 120

    with pytest.raises(RateLimitExceeded, match="daily token limit"):
        rl.acquire(MODEL, 6_000)


def test_usage_is_shared_through_the_database(tmp_path: Path) -> None:
    clock = Clock()
    limiter(tmp_path, clock, rpd=1).acquire(MODEL, 10)

    with pytest.raises(RateLimitExceeded):
        limiter(tmp_path, clock, rpd=1).acquire(MODEL, 10)


def test_fit_lowers_max_tokens_to_fit_the_minute_budget(tmp_path: Path) -> None:
    rl = limiter(tmp_path, Clock(), tpm=8_000)

    assert rl.fit(2_000, 4_096) == 4_096
    assert rl.fit(5_000, 4_096) == 3_000
    with pytest.raises(RateLimitExceeded, match="too large"):
        rl.fit(7_800, 4_096)


def test_estimates_over_count_the_prompt() -> None:
    assert estimate_prompt_tokens("hello world") > 2


def completion(content: str, total_tokens: int) -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(total_tokens=total_tokens),
    )


def test_groq_llm_lowers_max_tokens_and_records_usage(tmp_path: Path) -> None:
    clock = Clock()
    rl = limiter(tmp_path, clock, tpm=8_000)
    client = Mock()
    client.chat.completions.create.return_value = completion('{"a": 1}', 900)
    request = JsonRequest(
        model=MODEL,
        system="system",
        user="word " * 5_000,
        schema={"type": "object"},
        schema_name="test",
        max_tokens=4_096,
    )

    GroqLLM(client=client, limiter=rl).complete_json(request)

    sent = client.chat.completions.create.call_args.kwargs["max_completion_tokens"]
    assert 512 <= sent < 4_096
    rl.acquire(MODEL, 7_000)  # only the 900 used tokens count now
    assert clock.slept == []


def test_groq_llm_turns_limit_errors_into_llm_errors(tmp_path: Path) -> None:
    rl = limiter(tmp_path, Clock(), rpd=1)
    rl.acquire(MODEL, 10)
    request = JsonRequest(model=MODEL, system="s", user="u", schema={}, schema_name="t")

    with pytest.raises(LLMError, match="daily"):
        GroqLLM(client=Mock(), limiter=rl).complete_json(request)


def test_the_classifier_fails_open_when_the_quota_is_used_up(tmp_path: Path) -> None:
    rl = limiter(tmp_path, Clock(), rpd=1)
    rl.acquire("openai/gpt-oss-20b", 10)
    client = Mock()

    assert ScopeClassifier(client, limiter=rl).check("question") == GuardResult(True)
    client.chat.completions.create.assert_not_called()


def test_daily_limits_reset_at_utc_midnight(tmp_path: Path) -> None:
    clock = Clock()
    clock.now = 86_400 * 20 + 23 * 3600  # 23:00 UTC
    rl = limiter(tmp_path, clock, rpd=2)
    rl.acquire(MODEL, 100)
    rl.acquire(MODEL, 100)
    with pytest.raises(RateLimitExceeded):
        rl.acquire(MODEL, 100)

    clock.now += 2 * 3600  # 01:00 UTC the next day: a rolling window would still refuse
    rl.acquire(MODEL, 100)
