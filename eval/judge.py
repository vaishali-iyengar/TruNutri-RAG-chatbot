"""Citation precision judge (implementation-plan.md, 9.2; ARCHITECTURE.md §11.2).

For each rendered claim, an LLM reads the claim and the passages it cites and says
whether the passages support it:

- supported: every fact in the claim (numbers, foods, conditions, who it applies to)
  is stated in, or directly follows from, the cited passages;
- partial: the gist is there, but the claim adds, changes or over-generalises something;
- unsupported: the passages don't say it, or say something else.

Citation precision = supported claims / judged claims. One call per answer judges all
its claims, and replies go through the LLM cache, so re-runs are free and repeatable.
The judge is a different call from the generator (its own prompt, temperature 0) but
the same model; its reliability is hand-checked on a
sample (eval/results/judge_check.md).
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from guidance_rag.llm import LLM, JsonRequest, LLMError
from guidance_rag.models import Answer, Chunk

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """\
You check citations in answers built from official food, nutrition and food-safety \
guidance. For each numbered claim you get the passages it cites. Decide, from those \
passages only, whether they support the claim:

- supported: every fact in the claim is stated in the passages or follows directly \
from them: numbers and units, the food or nutrient, the conditions (raw or cooked, \
fridge or freezer) and who it applies to (adults, children, food businesses). \
Rewording, summarising and combining facts from the cited passages is fine.
- partial: the main point is in the passages, but the claim adds a detail, changes a \
number or condition, or states as general something the passages limit.
- unsupported: the passages don't say this, or say something different.

Be strict about numbers and conditions, and don't use your own knowledge. Give a short \
reason for every verdict."""


class Verdict(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class JudgedClaim:
    doc_id: str
    text: str
    chunk_ids: tuple[str, ...]
    verdict: Verdict | None  # None: the judge gave no verdict for this claim
    reason: str


class _Item(BaseModel):
    claim: int
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str


class _Reply(BaseModel):
    verdicts: list[_Item]


def judge_schema(n_claims: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "integer", "enum": list(range(1, n_claims + 1))},
                        "verdict": {
                            "type": "string",
                            "enum": ["supported", "partial", "unsupported"],
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["claim", "verdict", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def judge_message(
    question: str, claims: Sequence[tuple[str, Sequence[str]]], chunks: Mapping[str, Chunk]
) -> str:
    """The question, then each claim with the full text of the passages it cites."""
    parts = [f"<question>{question}</question>"]
    for i, (text, chunk_ids) in enumerate(claims, 1):
        passages = "\n".join(
            f'<passage chunk_id="{c}" section="{" > ".join(chunks[c].section_path)}">\n'
            f"{chunks[c].text}\n</passage>"
            for c in chunk_ids
            if c in chunks
        )
        parts.append(f'<claim n="{i}">\n<text>{text}</text>\n{passages}\n</claim>')
    return "\n\n".join(parts)


class Judge:
    def __init__(self, llm: LLM, chunks: Mapping[str, Chunk], model: str = DEFAULT_MODEL) -> None:
        self.llm = llm
        self.chunks = chunks
        self.model = model

    def judge(self, question: str, answer: Answer) -> list[JudgedClaim]:
        """A verdict for every claim in `answer` (verdict None where the judge failed)."""
        flat = [(s.doc_id, c.text, tuple(c.chunk_ids)) for s in answer.sections for c in s.claims]
        if not flat:
            return []
        request = JsonRequest(
            model=self.model,
            system=SYSTEM_PROMPT,
            user=judge_message(question, [(t, ids) for _, t, ids in flat], self.chunks),
            schema=judge_schema(len(flat)),
            schema_name="citation_verdicts",
            max_tokens=3072,  # the free tier's 8K tokens/minute must hold prompt + reply
            reasoning_effort="medium",
        )
        found: dict[int, _Item] = {}
        for attempt in (1, 2):
            try:
                response = self.llm.complete_json(request)
                if not response.complete:
                    raise LLMError(f"cut off ({response.finish_reason})")
                reply = _Reply.model_validate_json(response.content or "")
                found = {v.claim: v for v in reply.verdicts}
                break
            except (LLMError, ValidationError) as exc:
                log.warning("judge failed (attempt %d): %s", attempt, exc)
        return [
            JudgedClaim(
                doc_id,
                text,
                ids,
                Verdict(found[i].verdict) if i in found else None,
                found[i].reason if i in found else "no verdict from the judge",
            )
            for i, (doc_id, text, ids) in enumerate(flat, 1)
        ]
