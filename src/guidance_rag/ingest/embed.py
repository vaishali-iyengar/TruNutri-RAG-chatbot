"""Embeddings for chunks and queries (implementation-plan.md, 4.2).

`Embedder` is the interface the indexer and retriever use; the real model is a
sentence-transformers model (optional `embed` extra), and tests use a fake.
`CachedEmbedder` stores document vectors in SQLite keyed by a hash of the model
name and the text, so re-indexing embeds only chunks whose text changed.

`export_vectors` writes the vectors of the current chunks to a committed file,
`corpus/embeddings.sqlite`, in the cache's format. The Docker build seeds its cache from
it, so building the image (e.g. on Cloud Build, for Cloud Run) doesn't embed the corpus
again: that took ~40 min on 4 CPUs.
"""

import hashlib
import logging
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from guidance_rag.config import PROJECT_ROOT, EmbeddingConfig

log = logging.getLogger(__name__)

Vectors = npt.NDArray[np.float32]

DEFAULT_VECTORS_FILE = PROJECT_ROOT / "corpus" / "embeddings.sqlite"


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


def export_vectors(
    texts: Sequence[str],
    model: str,
    dest: Path = DEFAULT_VECTORS_FILE,
    cache_dir: Path | None = None,
    make_embedder: Callable[[], Embedder] | None = None,
) -> tuple[int, int]:
    """Write the vectors of `texts` (embedded with `model`) to `dest`, a fresh SQLite file
    in the cache's format, with nothing else in it. Texts the cache doesn't have are
    embedded first with `make_embedder()`, which is only called then. Returns (vectors
    written, texts newly embedded)."""
    cache_dir = cache_dir or EmbeddingConfig().cache_dir
    keyed = {cache_key(model, t): t for t in texts}
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = sqlite3.connect(cache_dir / "vectors.sqlite")
    cache.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vec BLOB)")
    have = {k for (k,) in cache.execute("SELECT key FROM vectors")}
    missing = [t for k, t in keyed.items() if k not in have]
    if missing:
        if make_embedder is None:
            raise ValueError(
                f"{len(missing)} text(s) aren't in the cache and no embedder was given"
            )
        embedder = CachedEmbedder(make_embedder(), cache_dir)
        if embedder.name != model:
            raise ValueError(f"embedder is {embedder.name!r}, expected {model!r}")
        embedder.embed_documents(missing)
        embedder.close()
    rows = []
    for key in sorted(keyed):
        (vec,) = cache.execute("SELECT vec FROM vectors WHERE key = ?", (key,)).fetchone()
        rows.append((key, vec))
    cache.close()

    tmp = dest.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    out = sqlite3.connect(tmp)
    out.execute("CREATE TABLE vectors (key TEXT PRIMARY KEY, vec BLOB)")
    out.executemany("INSERT INTO vectors VALUES (?, ?)", rows)
    out.commit()
    out.execute("VACUUM")
    out.close()
    tmp.replace(dest)
    return len(rows), len(missing)
