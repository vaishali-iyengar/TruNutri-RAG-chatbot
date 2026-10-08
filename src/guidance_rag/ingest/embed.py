"""Embeddings for chunks and queries (implementation-plan.md, 4.2).

`Embedder` is the interface the indexer and retriever use; the real model is a
sentence-transformers model (optional `embed` extra), and tests use a fake.
`CachedEmbedder` stores document vectors in SQLite keyed by a hash of the model
name and the text, so re-indexing embeds only chunks whose text changed.
"""

import hashlib
import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from guidance_rag.config import EmbeddingConfig

log = logging.getLogger(__name__)

Vectors = npt.NDArray[np.float32]


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        """One L2-normalised row per text."""
        ...

    def embed_query(self, text: str) -> Vectors:
        """One L2-normalised vector (shape: dim)."""
        ...


class SentenceTransformerEmbedder:
    """A sentence-transformers model on Apple MPS, CUDA or CPU (`uv sync --extra embed`)."""

    def __init__(self, config: EmbeddingConfig | None = None, device: str | None = None) -> None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on installed extras
            raise RuntimeError("Embedding needs the 'embed' extra: uv sync --extra embed") from exc
        self.config = config or EmbeddingConfig()
        if device is None:
            device = (
                "mps" if torch.backends.mps.is_available()
                else "cuda" if torch.cuda.is_available() else "cpu"
            )  # fmt: skip
        self._model = SentenceTransformer(self.config.model, device=device)
        self._model.max_seq_length = self.config.max_seq_length
        self._dim = int(self._model.get_sentence_embedding_dimension() or 0)

    @property
    def name(self) -> str:
        return self.config.model

    @property
    def dim(self) -> int:
        return self._dim

    def _encode(self, texts: Sequence[str]) -> Vectors:
        # Sort by length so each batch pads less, then restore the order.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vectors = self._model.encode(
            [texts[i] for i in order],
            batch_size=self.config.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 50,
        )
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        out[order] = vectors
        return out

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        return self._encode([self.config.document_prefix + t for t in texts])

    def embed_query(self, text: str) -> Vectors:
        return np.asarray(self._encode([self.config.query_prefix + text])[0], dtype=np.float32)


def cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


class CachedEmbedder:
    """Wraps an embedder with an on-disk cache of document vectors (queries aren't cached)."""

    def __init__(self, embedder: Embedder, cache_dir: Path | None = None) -> None:
        self.embedder = embedder
        cache_dir = cache_dir or EmbeddingConfig().cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(cache_dir / "vectors.sqlite")
        self._db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vec BLOB)")
        self.hits = 0
        self.misses = 0

    @property
    def name(self) -> str:
        return self.embedder.name

    @property
    def dim(self) -> int:
        return self.embedder.dim

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        keys = [cache_key(self.name, t) for t in texts]
        found: dict[str, bytes] = {}
        for start in range(0, len(keys), 500):  # stay under SQLite's variable limit
            batch = keys[start : start + 500]
            marks = ",".join("?" * len(batch))
            found.update(
                self._db.execute(f"SELECT key, vec FROM vectors WHERE key IN ({marks})", batch)
            )
        text_of = dict(zip(keys, texts, strict=True))
        missing = [k for k in text_of if k not in found]  # unique, in first-seen order
        self.hits += sum(1 for k in keys if k in found)
        self.misses += len(missing)
        if missing:
            log.info("embedding %d new text(s) with %s", len(missing), self.name)
            new = self.embedder.embed_documents([text_of[k] for k in missing])
            rows = [(k, v.astype(np.float32).tobytes()) for k, v in zip(missing, new, strict=True)]
            self._db.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?)", rows)
            self._db.commit()
            found.update(rows)
        return np.stack([np.frombuffer(found[k], dtype=np.float32) for k in keys])

    def embed_query(self, text: str) -> Vectors:
        return self.embedder.embed_query(text)

    def close(self) -> None:
        self._db.close()
