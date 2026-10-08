"""Grounded answer generator (implementation-plan.md, 6.3; ARCHITECTURE.md §6.5).

Sends the question and the evidence to the LLM with the §6.5 schema forced by strict
structured output, and parses the reply into per-document claims. A reply that is
invalid, cut off or doesn't match the schema is retried once with the error; if the
retry fails too, the generator returns None and the pipeline answers NOT_IN_CORPUS
rather than anything unchecked.

When the service itself fails (unreachable, timed out, out of quota) on every attempt,
there is no reply to judge, so the generator raises `LLMUnavailable` and the API reports
an error rather than a refusal (9.5).
"""

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

from guidance_rag.llm import LLM, JsonRequest, LLMError, LLMUnavailable, ReasoningEffort, remaining
from guidance_rag.models import Claim, DocAnswer, Evidence
from guidance_rag.prompts import SYSTEM_PROMPT, answer_schema, user_message

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"


class _Claim(BaseModel):
    doc_id: str
    text: str
    chunk_ids: list[str]


class _Reply(BaseModel):
    status: Literal["answered", "partial", "none"]
    claims: list[_Claim]
    not_covered: str | None


@dataclass(frozen=True)
class Generation:
    status: Literal["answered", "partial", "none"]
    sections: list[DocAnswer]
    not_covered: str | None
    raw: str  # the LLM's JSON, for tracing


class Generator:
    def __init__(
        self,
        llm: LLM,
        model: str = DEFAULT_MODEL,
        reasoning_effort: ReasoningEffort = "medium",
        max_tokens: int = 4096,
    ) -> None:
        self.llm = llm
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens

    def generate(self, question: str, evidence: Evidence) -> Generation | None:
        """Per-document claims for `question`, or None if no valid reply after a retry."""
        if not evidence.documents:
            return Generation("none", [], None, "")
        user = user_message(question, evidence)
        schema = answer_schema(evidence)
        error: str | None = None
        service_error: LLMError | None = None
        replied = False  # the model answered at least once, even with bad JSON
        for attempt in (1, 2):
            text = user if error is None else (
                f"{user}\n\nYour previous reply was rejected: {error}\n"
                "Reply again with JSON that matches the schema."
            )  # fmt: skip
            request = JsonRequest(
                model=self.model,
                system=SYSTEM_PROMPT,
                user=text,
                schema=schema,
                schema_name="grounded_answer",
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
            )
            try:
                response = self.llm.complete_json(request)
            except LLMError as exc:
                log.warning("generator: LLM call failed (attempt %d): %s", attempt, exc)
                # Groq rejects JSON that doesn't validate with a 400 json_validate_failed.
                malformed = "json_validate_failed" in str(exc)
                error = "its JSON was malformed" if malformed else "the request failed"
                replied |= malformed
                if not malformed:
                    service_error = exc
                    left = remaining()
                    if (left is not None and left <= 0) or is_daily_limit(exc):
                        break  # out of time, or out of quota for the day: don't retry
                continue
            replied = True
            if not response.complete:
                error = f"it was incomplete (finish_reason={response.finish_reason})"
                log.warning("generator: reply rejected (attempt %d): %s", attempt, error)
                continue
            try:
                reply = _Reply.model_validate_json(response.content or "")
            except ValidationError as exc:
                error = f"it did not match the schema: {exc.errors()[0]['msg']}"
                log.warning("generator: reply rejected (attempt %d): %s", attempt, error)
                continue
            return Generation(
                reply.status, group(reply.claims), reply.not_covered, response.content or ""
            )
        if not replied and service_error is not None:
            raise LLMUnavailable(f"the answer model is unavailable: {service_error}")
        return None


def is_daily_limit(exc: LLMError) -> bool:
    """Groq's daily quota (TPD/RPD) or our limiter's daily limit: a retry can't succeed."""
    text = str(exc)
    return "per day" in text or "daily" in text


def group(claims: list[_Claim]) -> list[DocAnswer]:
    """Claims grouped per document, in order of first appearance; empty claims and
    repeated chunk_ids within a claim removed."""
    sections: dict[str, list[Claim]] = {}
    for c in claims:
        text = c.text.strip()
        if text:
            sections.setdefault(c.doc_id, []).append(
                Claim(text=text, chunk_ids=list(dict.fromkeys(c.chunk_ids)))
            )
    return [DocAnswer(doc_id=d, claims=cs) for d, cs in sections.items()]
