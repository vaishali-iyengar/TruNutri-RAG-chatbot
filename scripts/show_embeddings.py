"""Show a few chunk embeddings stored in the local Qdrant index.

Reads .index/collection/guidance_chunks/storage.sqlite directly. Qdrant's local mode
keeps one row per point: `id` (pickled point id) and `point` (a pickled PointStruct
holding the vector and the chunk as payload). Reading the file, rather than opening a
QdrantClient, works even while another process holds the index lock.

    .venv/bin/python scripts/show_embeddings.py              # 3 chunks, first 8 dims
    .venv/bin/python scripts/show_embeddings.py -n 5 --dims 16
    .venv/bin/python scripts/show_embeddings.py --doc <doc_id> --random
    .venv/bin/python scripts/show_embeddings.py --json > embeddings.json
    .venv/bin/python scripts/show_embeddings.py --json --full   # whole vectors
"""

import argparse
import json
import pickle
import random
import sqlite3

import numpy as np

from guidance_rag.store import COLLECTION, DEFAULT_INDEX_DIR

DEFAULT_DB = DEFAULT_INDEX_DIR / "collection" / COLLECTION / "storage.sqlite"


def load_points(db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT point FROM points").fetchall()
    return [pickle.loads(blob) for (blob,) in rows]


def cosine_matrix(vectors: list[np.ndarray]) -> np.ndarray:
    m = np.stack(vectors)
    m = m / np.linalg.norm(m, axis=1, keepdims=True)
    return m @ m.T


def to_json(args: argparse.Namespace, total: int, chosen: list) -> dict:
    vectors = [np.asarray(p.vector, dtype=np.float32) for p in chosen]
    chunks = []
    for p, v in zip(chosen, vectors, strict=True):
        chunk = p.payload
        values = v if args.full else v[: args.dims]
        chunks.append(
            {
                "point_id": str(p.id),
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "section_path": chunk["section_path"],
                "text": chunk["text"],
                "vector": {
                    "dim": int(v.size),
                    "norm": round(float(np.linalg.norm(v)), 6),
                    "min": round(float(v.min()), 6),
                    "max": round(float(v.max()), 6),
                    "mean": round(float(v.mean()), 6),
                    "truncated": not args.full and v.size > args.dims,
                    "values": [round(float(x), 6) for x in values],
                },
            }
        )
    sims = (
        [[round(float(s), 4) for s in row] for row in cosine_matrix(vectors)]
        if len(vectors) > 1
        else []
    )
    return {
        "db": args.db,
        "total_points": total,
        "doc_id_filter": args.doc,
        "chunks": chunks,
        "cosine_similarity": sims,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", type=int, default=3, help="number of chunks to show")
    parser.add_argument("--dims", type=int, default=8, help="vector values to print")
    parser.add_argument("--doc", help="only chunks from this doc_id")
    parser.add_argument("--random", action="store_true", help="pick chunks at random")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--full", action="store_true", help="include the whole vector")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to storage.sqlite")
    args = parser.parse_args()

    points = load_points(args.db)
    total = len(points)
    if args.doc:
        points = [p for p in points if p.payload["doc_id"] == args.doc]
    points.sort(key=lambda p: p.payload["chunk_id"])
    chosen = random.sample(points, min(args.n, len(points))) if args.random else points[: args.n]

    if args.json:
        print(json.dumps(to_json(args, total, chosen), indent=2, ensure_ascii=False))
        return

    print(f"{args.db}: {total} points")
    if args.doc:
        print(f"{len(points)} points for doc_id={args.doc}")

    vectors = []
    for p in chosen:
        chunk = p.payload
        v = np.asarray(p.vector, dtype=np.float32)
        vectors.append(v)
        preview = " ".join(chunk["text"].split())[:160]
        head = ", ".join(f"{x:+.4f}" for x in v[: args.dims])
        print()
        print(f"point id : {p.id}")
        print(f"chunk_id : {chunk['chunk_id']}")
        print(f"section  : {' > '.join(chunk['section_path'])}")
        print(f"text     : {preview}{'...' if len(chunk['text']) > 160 else ''}")
        print(
            f"vector   : dim={v.size}  norm={np.linalg.norm(v):.4f}  "
            f"min={v.min():+.4f}  max={v.max():+.4f}  mean={v.mean():+.4f}"
        )
        print(f"first {min(args.dims, v.size):<3}: [{head}{', ...' if v.size > args.dims else ''}]")

    if len(vectors) > 1:
        sims = cosine_matrix(vectors)
        print("\ncosine similarity between the chunks above:")
        for i, row in enumerate(sims):
            print(f"  [{i}] " + "  ".join(f"{s:.3f}" for s in row))


if __name__ == "__main__":
    main()
