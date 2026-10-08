"""Test doubles for the answer layer: a fake LLM and evidence built from real chunks."""

import json
from collections.abc import Sequence
from typing import Any

from guidance_rag.llm import JsonRequest, LLMError, LLMResponse
from guidance_rag.models import DocEvidence, Evidence, ScoredChunk
from guidance_rag.store import load_chunks

CHUNKS = {c.chunk_id: c for c in load_chunks()}

# Real chunks used across the Phase 6 tests.
FRIDGE_POULTRY = "foodsafety-cold-storage:cold-food-storage-chart:3"  # fresh poultry 1 to 2 days
WHO_SALT = "who-healthy-diet:salt-sodium-and-potassium:2"  # less than 5 g of salt a day
DGI_OILS = "icmr-nin-dgi-2024:repeated-heating-of-oils:1"
WHO_FATS = "who-healthy-diet:fats:3"


def evidence(*chunk_ids: str, query: str = "q") -> Evidence:
    """Evidence holding these chunks, grouped by document in the given order."""
    groups: dict[str, list[ScoredChunk]] = {}
    for i, cid in enumerate(chunk_ids):
        chunk = CHUNKS[cid]
        groups.setdefault(chunk.doc_id, []).append(ScoredChunk(chunk=chunk, score=0.9 - i / 100))
    documents = [DocEvidence(doc_id=d, chunks=cs) for d, cs in groups.items()]
    return Evidence(
        query=query,
        docs_searched=sorted({CHUNKS[c].doc_id for c in CHUNKS}),
        documents=documents,
        ranked=[(c, 0.9) for c in chunk_ids],
        pool=list(chunk_ids),
    )


def reply(*sections: tuple[str, Sequence[tuple[str, Sequence[str]]]], status: str = "answered",
          not_covered: str | None = None) -> str:  # fmt: skip
    """The generator's JSON: reply(("doc", [("claim", ["chunk"])]), ...), as a flat claim list."""
    return json.dumps(
        {
            "status": status,
            "claims": [
                {"doc_id": d, "text": t, "chunk_ids": list(c)}
                for d, claims in sections
                for t, c in claims
            ],
            "not_covered": not_covered,
        }
    )


class FakeLLM:
    """Returns queued replies (a JSON string, an LLMResponse, or an exception to raise)
    and records every request."""

    def __init__(self, *replies: str | LLMResponse | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[JsonRequest] = []

    def complete_json(self, request: JsonRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("FakeLLM: no reply queued")
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(item, "stop")


class FakeRetriever:
    """Returns fixed evidence and records the calls."""

    def __init__(self, result: Evidence) -> None:
        self.result = result
        self.calls: list[tuple[Any, ...]] = []

    def retrieve(self, query: str, doc_ids: Any = None, sub_queries: Any = ()) -> Evidence:
        self.calls.append((query, doc_ids, tuple(sub_queries)))
        return self.result

    def close(self) -> None:
        pass


__all__ = ["LLMError"]
