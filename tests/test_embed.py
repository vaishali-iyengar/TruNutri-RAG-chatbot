"""Embedding cache (implementation-plan.md, 4.2), with a fake model."""

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from guidance_rag.ingest.embed import CachedEmbedder, Vectors, cache_key


class FakeEmbedder:
    """Deterministic unit vectors from a hash of the text; records what it embeds."""

    def __init__(self, name: str = "fake-model", dim: int = 16) -> None:
        self._name, self._dim = name, dim
        self.calls: list[list[str]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def dim(self) -> int:
        return self._dim

    def _vector(self, text: str) -> Vectors:
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        v = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32)
        return v / np.linalg.norm(v)

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        self.calls.append(list(texts))
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return np.stack([self._vector(t) for t in texts])

    def embed_query(self, text: str) -> Vectors:
        return self._vector(text)


@pytest.fixture
def fake() -> FakeEmbedder:
    return FakeEmbedder()


def test_second_run_is_served_from_the_cache(fake: FakeEmbedder, tmp_path: Path) -> None:
    cached = CachedEmbedder(fake, tmp_path)
    first = cached.embed_documents(["salt", "sugar"])
    second = cached.embed_documents(["salt", "sugar"])
    assert fake.calls == [["salt", "sugar"]]  # the model ran once
    assert np.array_equal(first, second)
    assert (cached.hits, cached.misses) == (2, 2)


def test_only_changed_texts_are_embedded(fake: FakeEmbedder, tmp_path: Path) -> None:
    cached = CachedEmbedder(fake, tmp_path)
    cached.embed_documents(["salt", "sugar"])
    out = cached.embed_documents(["salt", "fat", "fat"])
    assert fake.calls[-1] == ["fat"]  # duplicates are embedded once
    assert out.shape == (3, fake.dim)
    assert np.array_equal(out[1], out[2])


def test_cache_survives_a_restart(fake: FakeEmbedder, tmp_path: Path) -> None:
    CachedEmbedder(fake, tmp_path).embed_documents(["salt"])
    again = FakeEmbedder()
    CachedEmbedder(again, tmp_path).embed_documents(["salt"])
    assert again.calls == []


def test_a_different_model_does_not_reuse_vectors(fake: FakeEmbedder, tmp_path: Path) -> None:
    CachedEmbedder(fake, tmp_path).embed_documents(["salt"])
    other = FakeEmbedder(name="other-model")
    CachedEmbedder(other, tmp_path).embed_documents(["salt"])
    assert other.calls == [["salt"]]
    assert cache_key("a", "salt") != cache_key("b", "salt")


def test_queries_go_straight_to_the_model(fake: FakeEmbedder, tmp_path: Path) -> None:
    cached = CachedEmbedder(fake, tmp_path)
    vector = cached.embed_query("how long do eggs keep?")
    assert vector.shape == (fake.dim,)
    assert fake.calls == []  # embed_query doesn't go through the document cache
