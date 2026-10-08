"""Cross-encoder reranking (implementation-plan.md, 4.6).

`Reranker` is the interface the retriever uses; the real model is a
sentence-transformers cross-encoder (optional `embed` extra), and tests use a fake.
Scores go through a sigmoid, so they are 0-1 and comparable across queries, which
the thresholds `tau_doc` and `tau_answer` need.

Small models read at most 512 tokens. A longer text is scored in windows of whole
lines (each repeating its first line, the section path) and keeps its best window's
score, so an answer in the last rows of a table is not cut off.
"""

from collections.abc import Sequence
from typing import Protocol

from guidance_rag.config import RetrievalConfig
from guidance_rag.models import Chunk

WINDOW_MARGIN = 8  # tokens kept free for the separator tokens


class Reranker(Protocol):
    @property
    def name(self) -> str: ...

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """One relevance score (0-1) per text."""
        ...


def rerank_text(chunk: Chunk) -> str:
    """What the reranker reads: section path + body. Not the document label, which
    would give every chunk of a document the same head start."""
    return " > ".join(chunk.section_path) + "\n" + chunk.text


class TokenCounter(Protocol):
    def __call__(self, text: str) -> int: ...


def windows(text: str, budget: int, count: TokenCounter) -> list[str]:
    """Split `text` into pieces of whole lines of at most `budget` tokens, each starting
    with the text's first line. A single line over budget is left whole (and truncated)."""
    if count(text) <= budget:
        return [text]
    head, *lines = text.split("\n")
    room = budget - count(head) - 1
    pieces: list[list[str]] = [[]]
    used = 0
    for line in lines:
        n = count(line) + 1
        if pieces[-1] and used + n > room:
            pieces.append([])
            used = 0
        pieces[-1].append(line)
        used += n
    return [head + "\n" + "\n".join(p) for p in pieces]


class CrossEncoderReranker:
    """A sentence-transformers cross-encoder on Apple MPS, CUDA or CPU."""

    def __init__(self, config: RetrievalConfig | None = None, device: str | None = None) -> None:
        try:
            import torch
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on installed extras
            raise RuntimeError("Reranking needs the 'embed' extra: uv sync --extra embed") from exc
        self.config = config or RetrievalConfig()
        if device is None:
            device = (
                "mps" if torch.backends.mps.is_available()
                else "cuda" if torch.cuda.is_available() else "cpu"
            )  # fmt: skip
        self._sigmoid = torch.nn.Sigmoid()
        self._model = CrossEncoder(self.config.reranker_model, device=device)
        model_max = int(getattr(self._model.model.config, "max_position_embeddings", 0) or 0)
        limit = self.config.rerank_max_length
        self.max_length = min(limit, model_max) if model_max >= 128 else limit
        self._model.max_length = self.max_length

    @property
    def name(self) -> str:
        return self.config.reranker_model

    def _count(self, text: str) -> int:
        ids = self._model.tokenizer(text, add_special_tokens=False, verbose=False)["input_ids"]
        return len(ids)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        budget = self.max_length - self._count(query) - WINDOW_MARGIN
        pairs = [(i, w) for i, t in enumerate(texts) for w in windows(t, budget, self._count)]
        # Sort by length so each batch pads less.
        pairs.sort(key=lambda p: len(p[1]))
        scores = self._model.predict(
            [(query, w) for _, w in pairs],
            batch_size=self.config.rerank_batch_size,
            activation_fn=self._sigmoid,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        out = [0.0] * len(texts)
        for (i, _), s in zip(pairs, scores, strict=True):
            out[i] = max(out[i], float(s))
        return out
