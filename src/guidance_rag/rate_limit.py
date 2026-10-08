"""Client-side rate limits for Groq, so requests stay inside the account's quotas.

The free tier allows, per model: 30 requests and 8K tokens per minute, 1K requests and
200K tokens per day (`RateLimits`). Groq counts a request's prompt plus its
`max_completion_tokens` against the per-minute token limit before running it, so a
request larger than 8K tokens is refused outright.

`RateLimiter` keeps a log of requests per model in SQLite, so separate processes (the
app, an eval run) share one budget. Before each request it reserves the estimated
tokens: when a per-minute limit would be exceeded it sleeps until the window frees up;
when a daily limit (counted per UTC day, as Groq does) would be exceeded it raises
`RateLimitExceeded` rather than wait hours. After the reply, the reservation is replaced
by the tokens Groq reports.
"""

import logging
import math
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from guidance_rag.config import PROJECT_ROOT, Settings
from guidance_rag.ingest.chunker import count_tokens

log = logging.getLogger(__name__)

DEFAULT_USAGE_DB = PROJECT_ROOT / ".cache" / "llm" / "usage.sqlite"

MINUTE = 60.0
DAY = 24 * 60 * 60.0


def day_start(now: float) -> float:
    """Start of the UTC day containing `now`. Groq's daily quotas reset then, not on a
    rolling 24 hours: on 2026-10-08 the quota used up the evening before (IST) was back
    at 05:17 UTC while a rolling window would still have blocked it until 12:17 UTC."""
    return now - now % DAY


# Prompt tokens are counted with cl100k; gpt-oss uses o200k (harmony), which counts a
# little differently and wraps each message in format tokens. Over-estimate to be safe.
PROMPT_MARGIN = 1.15
MESSAGE_OVERHEAD = 64


class RateLimits(BaseModel):
    """Quotas for one model (Groq free tier for openai/gpt-oss-120b)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rpm: int = Field(default=30, ge=1)  # requests per minute
    rpd: int = Field(default=1_000, ge=1)  # requests per day
    tpm: int = Field(default=8_000, ge=1)  # tokens per minute (prompt + max completion)
    tpd: int = Field(default=200_000, ge=1)  # tokens per day
    min_completion: int = Field(default=512, ge=1)  # smallest max_tokens worth sending


class RateLimitExceeded(RuntimeError):
    """A request can't be sent within the limits: a daily quota is used up, or the
    request alone is larger than the per-minute token limit."""


def estimate_prompt_tokens(*texts: str) -> int:
    """An upper estimate of the prompt tokens for these messages (and schema)."""
    counted = sum(count_tokens(t) for t in texts)
    return math.ceil(counted * PROMPT_MARGIN) + MESSAGE_OVERHEAD * len(texts)


class RateLimiter:
    def __init__(
        self,
        limits: RateLimits | None = None,
        db_path: Path = DEFAULT_USAGE_DB,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.limits = limits or RateLimits()
        self.clock = clock
        self.sleep = sleep
        self._lock = threading.Lock()
        self._blocked: dict[str, float] = {}  # model -> clock time its daily quota resets
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, model TEXT, ts REAL, "
            "tokens INTEGER)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS usage_model_ts ON usage (model, ts)")
        self._db.commit()

    def fit(self, prompt_tokens: int, max_tokens: int) -> int:
        """The completion budget to request: `max_tokens`, lowered so that prompt plus
        completion fit in one minute's tokens. Raises if too little room is left."""
        room = self.limits.tpm - prompt_tokens
        if room < self.limits.min_completion:
            raise RateLimitExceeded(
                f"request too large: ~{prompt_tokens} prompt tokens leave {max(room, 0)} for "
                f"the reply under the {self.limits.tpm} tokens-per-minute limit"
            )
        if max_tokens > room:
            log.info("rate limit: max_tokens lowered from %d to %d to fit", max_tokens, room)
            return room
        return max_tokens

    def acquire(self, model: str, tokens: int, max_wait: float | None = None) -> int:
        """Reserve `tokens` for one request to `model`, waiting for the per-minute window
        if needed, but never longer than `max_wait` seconds in total (None = no limit).
        Returns a ticket for `settle`."""
        if tokens > self.limits.tpm:
            raise RateLimitExceeded(
                f"request needs ~{tokens} tokens, over the {self.limits.tpm} per-minute limit"
            )
        blocked = self._blocked.get(model, 0.0) - self.clock()
        if blocked > 0:
            raise RateLimitExceeded(
                f"daily quota for {model} used up (Groq says it frees up in {blocked:.0f} s)"
            )
        waited = 0.0
        while True:
            with self._lock:
                now = self.clock()
                with self._db:  # one transaction, so other processes see a consistent log
                    self._db.execute("DELETE FROM usage WHERE ts <= ?", (now - DAY,))
                    self._check_daily(model, tokens, now)
                    wait = self._minute_wait(model, tokens, now)
                    if wait <= 0:
                        cur = self._db.execute(
                            "INSERT INTO usage (model, ts, tokens) VALUES (?, ?, ?)",
                            (model, now, tokens),
                        )
                        return int(cur.lastrowid or 0)
            if max_wait is not None and waited + wait > max_wait:
                raise RateLimitExceeded(
                    f"the {model} quota frees up in {wait:.0f} s, past the request's time limit"
                )
            log.info("rate limit: waiting %.1f s for %s", wait, model)
            self.sleep(wait)
            waited += wait

    def block(self, model: str, seconds: float) -> None:
        """Groq refused `model` for its daily quota: fail its requests at once for
        `seconds` instead of sending them (and waiting on retries) to be refused again.
        Groq's count can run ahead of ours, which only sees this machine's requests."""
        with self._lock:
            self._blocked[model] = self.clock() + seconds
        log.warning("rate limit: %s daily quota used up; blocked for %.0f s", model, seconds)

    def settle(self, ticket: int, tokens: int) -> None:
        """Replace a reservation with the tokens the request actually used."""
        with self._lock, self._db:
            self._db.execute("UPDATE usage SET tokens = ? WHERE id = ?", (tokens, ticket))

    def _check_daily(self, model: str, tokens: int, now: float) -> None:
        requests, used = self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(tokens), 0) FROM usage WHERE model = ? AND ts > ?",
            (model, day_start(now)),
        ).fetchone()
        if requests + 1 > self.limits.rpd:
            raise RateLimitExceeded(
                f"daily request limit reached for {model} ({requests}/{self.limits.rpd})"
            )
        if used + tokens > self.limits.tpd:
            raise RateLimitExceeded(
                f"daily token limit reached for {model} ({used} + ~{tokens} > {self.limits.tpd})"
            )

    def _minute_wait(self, model: str, tokens: int, now: float) -> float:
        """Seconds until one more request of `tokens` fits in the last minute's log."""
        rows = self._db.execute(
            "SELECT ts, tokens FROM usage WHERE model = ? AND ts > ? ORDER BY ts",
            (model, now - MINUTE),
        ).fetchall()
        requests, used = len(rows), sum(t for _, t in rows)
        wait = 0.0
        for ts, spent in rows:  # oldest first: each one leaves the window at ts + MINUTE
            if requests < self.limits.rpm and used + tokens <= self.limits.tpm:
                break
            requests, used = requests - 1, used - spent
            wait = ts + MINUTE - now + 0.05
        return wait

    def close(self) -> None:
        self._db.close()


_RETRY_IN = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?")


def daily_quota_reset(message: str) -> float | None:
    """Seconds until a Groq daily limit (TPD/RPD) frees up, read from a 429 message such as
    "... tokens per day (TPD) ... Please try again in 9m13.8s"; None if not a daily limit."""
    if "per day" not in message:
        return None
    m = _RETRY_IN.search(message)
    if not m or not any(m.groups()):
        return 60.0
    hours, minutes, seconds = (float(g) if g else 0.0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def limiter_from_settings(settings: Settings) -> RateLimiter:
    limits = RateLimits(
        rpm=settings.groq_rpm, rpd=settings.groq_rpd, tpm=settings.groq_tpm, tpd=settings.groq_tpd
    )
    return RateLimiter(limits)
