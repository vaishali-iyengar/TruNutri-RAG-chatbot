"""Search indexes over the chunks (implementation-plan.md, 4.3-4.4).

- `VectorStore`: dense vectors in Qdrant. Local mode (a folder, no server) by
  default; pass a URL to use a Qdrant server (Docker, 8.5). The whole chunk is
  stored as payload, so a search returns everything needed for citations.
- `BM25Index`: keyword search, rebuilt in memory from corpus/chunks/ at start-up
  (903 chunks take milliseconds), so there is nothing to persist or keep in sync.

Both support the same `doc_ids` filter, applied before ranking.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.ingest.chunker import DEFAULT_CHUNKS_DIR, read_chunks
from guidance_rag.ingest.embed import Vectors
from guidance_rag.models import Chunk

DEFAULT_INDEX_DIR = PROJECT_ROOT / ".index"
COLLECTION = "guidance_chunks"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def load_chunks(chunks_dir: Path = DEFAULT_CHUNKS_DIR) -> list[Chunk]:
    """Every chunk in corpus/chunks/, in a stable order (by file, then position)."""
    return [c for path in sorted(chunks_dir.glob("*.jsonl")) for c in read_chunks(path)]


def point_id(chunk_id: str) -> str:
    """A stable UUID for a chunk, so re-indexing overwrites instead of duplicating."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"guidance-rag:{chunk_id}"))


# --- Dense vectors (4.3) -------------------------------------------------------------


def _doc_filter(doc_ids: Sequence[str] | None) -> models.Filter | None:
    if not doc_ids:
        return None
    return models.Filter(
        must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=list(doc_ids)))]
    )


class VectorStore:
    def __init__(
        self,
        path: Path = DEFAULT_INDEX_DIR,
        url: str | None = None,
        collection: str = COLLECTION,
    ) -> None:
        self.local = url is None
        self.client = QdrantClient(url=url) if url else QdrantClient(path=str(path))
        self.collection = collection

    def close(self) -> None:
        self.client.close()

    def exists(self) -> bool:
        return self.client.collection_exists(self.collection)

    def ensure_collection(self, dim: int, recreate: bool = False) -> None:
        """Create the collection; recreate it if asked or if the vector size changed."""
        if self.exists():
            info = self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            size = vectors.size if isinstance(vectors, models.VectorParams) else None
            if not recreate and size == dim:
                return
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        if not self.local:  # payload indexes have no effect in local mode
            for field in ("doc_id", "domain", "block_type"):
                self.client.create_payload_index(
                    self.collection, field, field_schema=models.PayloadSchemaType.KEYWORD
                )

    def replace_document(self, doc_id: str, chunks: Sequence[Chunk], vectors: Vectors) -> None:
        """Delete a document's points, then insert its current chunks."""
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk is required")
        if any(c.doc_id != doc_id for c in chunks):
            raise ValueError(f"all chunks must belong to {doc_id}")
        self.delete_document(doc_id)
        points = [
            models.PointStruct(
                id=point_id(c.chunk_id),
                vector=v.astype(np.float32).tolist(),
                payload=c.model_dump(mode="json"),
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
        for start in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[start : start + 256])

    def delete_document(self, doc_id: str) -> None:
        self.client.delete(
            self.collection, points_selector=models.FilterSelector(filter=_doc_filter([doc_id]))
        )

    def count(self, doc_id: str | None = None) -> int:
        doc_ids = [doc_id] if doc_id else None
        return self.client.count(self.collection, count_filter=_doc_filter(doc_ids)).count

    def search(
        self, vector: Vectors, doc_ids: Sequence[str] | None = None, limit: int = 40
    ) -> list[Hit]:
        """Nearest chunks by cosine similarity, pre-filtered by document."""
        result = self.client.query_points(
            self.collection,
            query=vector.astype(np.float32).tolist(),
            query_filter=_doc_filter(doc_ids),
            limit=limit,
            with_payload=True,
        )
        return [Hit(Chunk.model_validate(p.payload), p.score) for p in result.points]

    def vectors(self, chunk_ids: Sequence[str]) -> dict[str, Vectors]:
        """The stored vectors of these chunks (missing ones are left out)."""
        points = self.client.retrieve(
            self.collection,
            ids=[point_id(c) for c in chunk_ids],
            with_payload=["chunk_id"],
            with_vectors=True,
        )
        out: dict[str, Vectors] = {}
        for p in points:
            if p.payload and isinstance(p.vector, list):
                out[str(p.payload["chunk_id"])] = np.asarray(p.vector, dtype=np.float32)
        return out


# --- Keywords (4.4) ------------------------------------------------------------------

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
    }
)

_TOKEN = re.compile(
    r"\d+(?:\.\d+)?°[cf]"  # temperatures: 4°c, 18°c, 40°f
    r"|\d+(?:\.\d+)?"  # numbers, decimals
    r"|[a-z]+(?:/[a-z]+)+"  # units and pairs: mg/kg, gmp/ghp
    r"|[a-z]+"  # words
)


def tokenize(text: str) -> list[str]:
    """BM25 tokens: lowercase words (light plural folding), numbers, and units kept whole.

    "4 °C", "4°C" and "4ºC" all give "4°c" (plus "4"); "3–4 days", "3-4 days" and
    "3 to 4 days" all give "3", "4", "day".
    """
    text = text.lower().replace("º", "°")
    text = re.sub(r"(\d)\s*°\s*([cf])\b", r"\1°\2", text)
    tokens = []
    for token in _TOKEN.findall(text):
        if token in STOPWORDS:
            continue
        if token[0].isdigit():
            tokens.append(token)
            if "°" in token:
                tokens.append(token.split("°")[0])  # the bare number matches "4 degrees"
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]  # eggs -> egg, days -> day, vegetables -> vegetable
        tokens.append(token)
    return tokens


def bm25_text(chunk: Chunk) -> str:
    """What BM25 indexes: section path + body. Not the document label, which would add
    the same words to every chunk of a document."""
    return " ".join(chunk.section_path) + "\n" + chunk.text


class BM25Index:
    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self.chunks = list(chunks)
        self._bm25 = BM25Okapi([tokenize(bm25_text(c)) for c in self.chunks])
        self._doc_ids = np.array([c.doc_id for c in self.chunks])

    @classmethod
    def from_dir(cls, chunks_dir: Path = DEFAULT_CHUNKS_DIR) -> "BM25Index":
        return cls(load_chunks(chunks_dir))

    def search(
        self, query: str, doc_ids: Sequence[str] | None = None, limit: int = 40
    ) -> list[Hit]:
        """Best-matching chunks for the query, pre-filtered by document. Chunks with no
        query term (score 0) are not returned."""
        terms = tokenize(query)
        if not terms or not self.chunks:
            return []
        scores = np.asarray(self._bm25.get_scores(terms), dtype=np.float64)
        if doc_ids:
            allowed = np.isin(self._doc_ids, list(doc_ids))
        else:
            allowed = np.ones(len(scores), dtype=bool)
        candidates = np.flatnonzero(allowed & (scores > 0))
        best = candidates[np.argsort(-scores[candidates], kind="stable")][:limit]
        return [Hit(self.chunks[i], float(scores[i])) for i in best]


# --- Table rows ----------------------------------------------------------------------------

_RULE_LINE = re.compile(r"^\|[\s|:-]+\|$")  # the |---|---| line under a header row


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(chunk: Chunk) -> list[tuple[str, str]]:
    """(label, search line) for each row of a table chunk. The line carries the table's
    caption and column names: "Table 1.3. Average values … (Per 100g raw weight)\nMilk:
    Protein (g) 3.1; Fat (g) 4.2; …", with label "Milk". Handles both table layouts the
    chunker writes: Markdown rows under a header row, and wide tables written one
    "column: value; …" line per row (label: the row's first value)."""
    lines = [ln.strip() for ln in chunk.text.splitlines() if ln.strip()]
    caption = " ".join(
        ln for ln in lines if not ln.startswith(("|", "Columns:")) and ": " not in ln[:60]
    )[:300]
    head = f"{caption}\n" if caption else ""
    table = [ln for ln in lines if ln.startswith("|") and not _RULE_LINE.match(ln)]
    rows: list[tuple[str, str]] = []
    if len(table) >= 2:
        header = _cells(table[0])
        for ln in table[1:]:
            cells = _cells(ln)
            pairs = [f"{h} {v}" for h, v in zip(header[1:], cells[1:], strict=False) if v]
            if cells and cells[0]:
                rows.append((cells[0], f"{head}{cells[0]}: {'; '.join(pairs)}"))
    else:  # wide layout: "Food groups (2000 Kcal): Milk/ curd (ml); Foods …: 300; …"
        for ln in lines:
            if ln.count(": ") >= 2 and "; " in ln:
                rows.append((ln.split("; ", 1)[0].split(": ", 1)[1], f"{head}{ln}"))
    return rows


@dataclass(frozen=True)
class RowHit:
    chunk: Chunk
    row: str  # the matching row's search line
    score: float


class TableRowIndex:
    """BM25 over the rows of every table chunk, built in memory at start-up.

    A table is mostly numbers under a heading that may not name what it lists (ICMR's
    Table 1.3, protein per 100 g of each food group, sits under "What are nutrient
    requirements, RDA & EAR"), so "How much protein does milk have?" ranked it ~60th by
    chunk and it never reached the reranker. Searching rows lets the "Milk" row bring its
    table into the pool, and gives the reranker one row to score instead of the table.

    A row matches only when its label shares a word with the query ("milk" for the
    "Milk" row): matching on column names or captions alone pulled unrelated tables into
    the pools of 11 of 29 golden questions.
    """

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self.rows: list[tuple[Chunk, str, frozenset[str]]] = [
            (c, row, frozenset(tokenize(label)))
            for c in chunks
            if c.table_id
            for label, row in table_rows(c)
        ]
        self._bm25 = BM25Okapi([tokenize(r) for _, r, _ in self.rows]) if self.rows else None
        self._doc_ids = np.array([c.doc_id for c, _, _ in self.rows])

    def search(
        self, query: str, doc_ids: Sequence[str] | None = None, limit: int = 5
    ) -> list[RowHit]:
        """The best-matching rows whose label shares a query word, one per table chunk."""
        terms = tokenize(query)
        if not terms or self._bm25 is None:
            return []
        scores = np.asarray(self._bm25.get_scores(terms), dtype=np.float64)
        allowed = np.isin(self._doc_ids, list(doc_ids)) if doc_ids else np.ones(len(scores), bool)
        query_terms = set(terms)
        hits: list[RowHit] = []
        seen: set[str] = set()
        for i in np.argsort(-scores, kind="stable"):
            if len(hits) >= limit or scores[i] <= 0:
                break
            chunk, row, label = self.rows[i]
            if allowed[i] and chunk.chunk_id not in seen and label & query_terms:
                seen.add(chunk.chunk_id)
                hits.append(RowHit(chunk, row, float(scores[i])))
        return hits
