"""Hybrid retrieval: candidate pool, rerank, evidence selection (implementation-plan.md 4.5-4.6).

For a query and an optional document filter:

1. Dense and BM25 search, fused with Reciprocal Rank Fusion, once across the documents
   in scope (`global_k` kept) and once inside each of them (`per_doc_k` kept each).
   The per-document lists let a 5-chunk document reach the reranker when a 313-chunk
   document fills the whole global list.
2. When a piece of a split table is in the pool, its sibling pieces are added (up to
   `table_expand`), since the row that answers may sit in a piece that ranked lower.
   Then near-copies of a chunk already kept from the same document are dropped.
3. A cross-encoder scores the pool. The ranking fuses the pool order (hybrid search)
   with the rerank order by RRF: on the golden set this beats either alone (MRR 0.91
   vs 0.87 and 0.78). The rerank score still decides what is evidence: documents
   qualify at `tau_doc` (or `tau_doc_extra` once one has), and their chunks are taken
   in ranking order: the top `per_doc_max` per document, or up to `single_doc_max`
   when only one document qualifies.

The steps are plain functions, so they can be tested with fake scores.
"""

import logging
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from guidance_rag.config import RetrievalConfig
from guidance_rag.ingest.embed import Embedder, Vectors
from guidance_rag.models import Chunk, DocEvidence, Evidence, ScoredChunk
from guidance_rag.query.rerank import Reranker, rerank_text
from guidance_rag.store import DEFAULT_INDEX_DIR, BM25Index, VectorStore

log = logging.getLogger(__name__)


# --- Steps ---------------------------------------------------------------------------


def rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> list[str]:
    """Fuse ranked lists of IDs by Reciprocal Rank Fusion: sum of 1 / (k + rank).

    Ties keep first-seen order, so the first list wins them."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)
    return sorted(scores, key=lambda item: -scores[item])


def build_pool(
    global_ids: Sequence[str],
    per_doc_ids: Mapping[str, Sequence[str]],
    global_k: int,
    per_doc_k: int,
) -> list[str]:
    """The global top `global_k`, then each document's top `per_doc_k`, without repeats."""
    pool = list(global_ids[:global_k])
    for ids in per_doc_ids.values():
        pool.extend(ids[:per_doc_k])
    return list(dict.fromkeys(pool))


def expand_tables(
    pool: Sequence[str],
    tables: Mapping[str, Sequence[str]],
    chunk_table: Mapping[str, str],
    limit: int,
) -> list[str]:
    """Add the other pieces of every split table that has a piece in the pool, each
    table's pieces right after its first one, at most `limit` pieces per table."""
    out: list[str] = []
    for chunk_id in pool:
        table_id = chunk_table.get(chunk_id)
        siblings = tables.get(table_id, ()) if table_id else ()
        out.append(chunk_id)
        out.extend(siblings[:limit])
    return list(dict.fromkeys(out))


def prune(pool: Sequence[Chunk], vectors: Mapping[str, Vectors], dup_cosine: float) -> list[Chunk]:
    """Drop, in pool order, near-copies: chunks whose cosine to a chunk already kept from
    the same document is above `dup_cosine` (typically paragraphs repeated as overlap).

    Pieces of one table are never near-copies of each other: they look alike but hold
    different rows. (The evidence keeps at most `table_cap` of them; see `select`.)
    """
    kept: list[Chunk] = []
    for chunk in pool:
        v = vectors.get(chunk.chunk_id)
        if v is not None and any(
            other.doc_id == chunk.doc_id
            and not (chunk.table_id and other.table_id == chunk.table_id)
            and other.chunk_id in vectors
            and float(v @ vectors[other.chunk_id]) > dup_cosine
            for other in kept
        ):
            continue
        kept.append(chunk)
    return kept


def select(
    ranked: Sequence[ScoredChunk],
    config: RetrievalConfig,
    tau: float,
    tau_extra: float | None = None,
) -> list[DocEvidence]:
    """Group the ranked chunks that pass the threshold by document, in ranking order.

    Two thresholds: a document qualifies when its best chunk scores at least `tau`; once
    one has, other documents also qualify at `tau_extra` (lower), so the second voice of
    a cross-document question isn't lost. With no chunk at `tau` there is no evidence at
    all, which keeps unanswerable questions empty. Each document keeps its chunks scoring
    at least its own threshold.

    With several documents: the top `per_doc_max` of each of the best `max_docs`, then the
    weakest extra chunks are dropped until `max_chunks` remain; a document never loses its
    best chunk. With one document: up to `single_doc_max` of its chunks.
    """
    ordered = list(ranked)
    if not ordered or max(sc.score for sc in ordered) < tau:
        return []
    low = tau if tau_extra is None else min(tau, tau_extra)
    best: dict[str, float] = {}
    for sc in ordered:
        best[sc.chunk.doc_id] = max(best.get(sc.chunk.doc_id, 0.0), sc.score)
    threshold = {d: tau if b >= tau else low for d, b in best.items()}

    by_doc: dict[str, list[ScoredChunk]] = {}
    per_table: Counter[tuple[str, str]] = Counter()
    for sc in ordered:
        if sc.score < threshold[sc.chunk.doc_id]:
            continue
        if sc.chunk.table_id:
            table = (sc.chunk.doc_id, sc.chunk.table_id)
            if per_table[table] >= config.table_cap:
                continue
            per_table[table] += 1
        by_doc.setdefault(sc.chunk.doc_id, []).append(sc)

    if len(by_doc) == 1:
        ((doc_id, chunks),) = by_doc.items()
        return [DocEvidence(doc_id=doc_id, chunks=chunks[: config.single_doc_max])]

    max_docs = min(config.max_docs, config.max_chunks)
    chosen = {d: cs[: config.per_doc_max] for d, cs in list(by_doc.items())[:max_docs]}
    while sum(len(cs) for cs in chosen.values()) > config.max_chunks:
        weakest = min((d for d in chosen if len(chosen[d]) > 1), key=lambda d: chosen[d][-1].score)
        chosen[weakest].pop()
    return [DocEvidence(doc_id=d, chunks=cs) for d, cs in chosen.items()]


# --- Retriever -----------------------------------------------------------------------


class Retriever:
    def __init__(
        self,
        store: VectorStore,
        bm25: BM25Index,
        embedder: Embedder,
        reranker: Reranker | None,
        config: RetrievalConfig | None = None,
    ) -> None:
        self.config = config or RetrievalConfig()
        if self.config.rerank and reranker is None:
            raise ValueError("config.rerank is on but no reranker was given")
        if not (self.config.dense or self.config.bm25):
            raise ValueError("turn on dense search, BM25 or both")
        self.store, self.bm25, self.embedder, self.reranker = store, bm25, embedder, reranker
        self._chunks = {c.chunk_id: c for c in bm25.chunks}
        self.doc_ids = sorted({c.doc_id for c in bm25.chunks})
        # table_id is unique within a document only ("p33-t1"), so key tables by both.
        self._tables: dict[str, list[str]] = defaultdict(list)
        self._chunk_table: dict[str, str] = {}
        for c in bm25.chunks:
            if c.table_id:
                key = f"{c.doc_id}/{c.table_id}"
                self._tables[key].append(c.chunk_id)
                self._chunk_table[c.chunk_id] = key

    def close(self) -> None:
        self.store.close()

    def _search(self, query: str, vector: Vectors, doc_ids: Sequence[str] | None) -> list[str]:
        """Dense and/or BM25 top `search_k`, fused."""
        k, rankings = self.config.search_k, []
        if self.config.dense:
            hits = self.store.search(vector, doc_ids=doc_ids, limit=k)
            for h in hits:
                self._chunks.setdefault(h.chunk.chunk_id, h.chunk)
            rankings.append([h.chunk.chunk_id for h in hits])
        if self.config.bm25:
            rankings.append([h.chunk.chunk_id for h in self.bm25.search(query, doc_ids, limit=k)])
        return rrf(rankings, self.config.rrf_k)

    def candidates(self, query: str, vector: Vectors, doc_ids: Sequence[str]) -> list[Chunk]:
        """The pruned candidate pool for `doc_ids` (4.5)."""
        cfg = self.config
        filtered = doc_ids if set(doc_ids) != set(self.doc_ids) else None
        global_ids = self._search(query, vector, filtered)
        per_doc: dict[str, list[str]] = {}
        if cfg.per_doc_k and len(doc_ids) > 1:
            per_doc = {d: self._search(query, vector, [d]) for d in doc_ids}
        ids = build_pool(global_ids, per_doc, cfg.global_k, cfg.per_doc_k)
        ids = expand_tables(ids, self._tables, self._chunk_table, cfg.table_expand)
        pool = [self._chunks[c] for c in ids]
        vectors = self.store.vectors(ids)
        return prune(pool, vectors, cfg.dup_cosine)

    def retrieve(
        self,
        query: str,
        doc_ids: Sequence[str] | None = None,
        sub_queries: Sequence[str] = (),
    ) -> Evidence:
        """Evidence for `query`, from `doc_ids` only when given (else every document).

        `sub_queries` (the halves of a two-part question) are searched too, and each
        chunk keeps its best rerank score over the queries that found it (each query
        reranks only its own candidates)."""
        if doc_ids:
            unknown = sorted(set(doc_ids) - set(self.doc_ids))
            if unknown:
                raise ValueError(f"not in the index: {unknown}")
        scope = list(dict.fromkeys(doc_ids)) if doc_ids else list(self.doc_ids)
        timings: dict[str, float] = {}

        queries = list(dict.fromkeys([query, *sub_queries]))

        start = time.perf_counter()
        vectors = [self.embedder.embed_query(q) for q in queries]
        timings["embed"] = _ms(start)

        start = time.perf_counter()
        found = [
            [c.chunk_id for c in self.candidates(q, v, scope)]
            for q, v in zip(queries, vectors, strict=True)
        ]
        pool = [self._chunks[c] for c in dict.fromkeys(c for ids in found for c in ids)]
        timings["search"] = _ms(start)

        start = time.perf_counter()
        if self.config.rerank and self.reranker is not None:
            # Each query reranks the chunks it found, not the whole pool: scoring every
            # pooled chunk against every query made two-part questions take 6.4 s (9.3).
            text_of = {c.chunk_id: rerank_text(c) for c in pool}
            best: dict[str, float] = {}
            for q, own in zip(queries, found, strict=True):
                for c, s in zip(
                    own, self.reranker.score(q, [text_of[c] for c in own]), strict=True
                ):
                    best[c] = max(best.get(c, 0.0), s)
            ids = [c.chunk_id for c in pool]
            scores = [best[c] for c in ids]
            tau, tau_extra = self.config.tau_doc, self.config.tau_doc_extra
        else:  # keep the pool order; no threshold
            scores = [1.0 - i / len(pool) for i in range(len(pool))]
            tau, tau_extra = 0.0, 0.0
        score_of = {c.chunk_id: s for c, s in zip(pool, scores, strict=True)}
        by_score = sorted(score_of, key=lambda c: -score_of[c])
        order = rrf([[c.chunk_id for c in pool], by_score], self.config.rrf_k)
        ranked = [ScoredChunk(chunk=self._chunks[c], score=score_of[c]) for c in order]
        timings["rerank"] = _ms(start)

        documents = select(ranked, self.config, tau, tau_extra)
        log.info(
            "retrieved %d chunks from %d docs (pool %d) in %.0f ms",
            sum(len(d.chunks) for d in documents),
            len(documents),
            len(pool),
            sum(timings.values()),
        )
        return Evidence(
            query=query,
            docs_searched=scope,
            documents=documents,
            ranked=[(sc.chunk.chunk_id, sc.score) for sc in ranked],
            pool=[c.chunk_id for c in pool],
            timings_ms=timings,
        )


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def load_retriever(
    config: RetrievalConfig | None = None,
    index_dir: Path = DEFAULT_INDEX_DIR,
    qdrant_url: str | None = None,
) -> Retriever:
    """A retriever over the built index with the real models (`uv sync --extra embed`)."""
    from guidance_rag.ingest.embed import SentenceTransformerEmbedder
    from guidance_rag.query.rerank import CrossEncoderReranker

    config = config or RetrievalConfig()
    store = VectorStore(path=index_dir, url=qdrant_url)
    if not store.exists():
        store.close()
        raise RuntimeError("no index: run `python -m guidance_rag.ingest index` first")
    reranker = CrossEncoderReranker(config) if config.rerank else None
    return Retriever(store, BM25Index.from_dir(), SentenceTransformerEmbedder(), reranker, config)
