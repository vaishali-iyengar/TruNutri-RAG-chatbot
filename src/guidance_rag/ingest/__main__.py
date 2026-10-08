"""Ingestion command line.

python -m guidance_rag.ingest fetch [--doc DOC_ID ...] [--refresh] [--include-reserve]
python -m guidance_rag.ingest check [--doc DOC_ID ...]
python -m guidance_rag.ingest parse [--doc DOC_ID ...] [--dump] [--full] [--save]
python -m guidance_rag.ingest chunk [--doc DOC_ID ...]
python -m guidance_rag.ingest index [--doc DOC_ID ...] [--force]
python -m guidance_rag.ingest vectors        # write corpus/embeddings.sqlite for the Docker build
"""

import argparse
import logging
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.ingest.check import check_raw_file
from guidance_rag.ingest.chunker import DEFAULT_CHUNKS_DIR, chunk_document, write_chunks
from guidance_rag.ingest.embed import (
    DEFAULT_VECTORS_FILE,
    CachedEmbedder,
    SentenceTransformerEmbedder,
    export_vectors,
)
from guidance_rag.ingest.fetch import DEFAULT_RAW_DIR, FetchStatus, fetch_all, make_client
from guidance_rag.ingest.index import build_index
from guidance_rag.ingest.parse import DEFAULT_PARSED_DIR, parse_document, save_parsed
from guidance_rag.ingest.qc import DEFAULT_QC_DIR, write_qc
from guidance_rag.ingest.tree import Document, iter_sections, outline, walk
from guidance_rag.models import DocumentStatus, SourceDocument
from guidance_rag.registry import DEFAULT_REGISTRY_PATH, Registry, load_registry, save_registry
from guidance_rag.store import DEFAULT_INDEX_DIR, VectorStore


def _select(
    registry: Registry, doc_ids: Sequence[str], include_reserve: bool
) -> list[SourceDocument]:
    if doc_ids:
        return [registry.get(d) for d in doc_ids]
    statuses = [DocumentStatus.INCLUDED]
    if include_reserve:
        statuses.append(DocumentStatus.RESERVE)
    return registry.with_status(*statuses)


def cmd_fetch(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    docs = _select(registry, args.doc, args.include_reserve)
    with make_client() as client:
        results = fetch_all(docs, client, raw_dir=args.raw_dir, refresh=args.refresh)

    for r in results:
        size = f"{r.size / 1_048_576:6.1f} MB" if r.size else " " * 9
        detail = r.error or str(r.path.relative_to(args.raw_dir.parent.parent))
        print(f"{r.status.value:<10} {r.doc.doc_id:<32} {size}  {detail}")
        if r.status is not FetchStatus.FAILED:
            registry.replace(r.doc)

    if any(r.status in (FetchStatus.NEW, FetchStatus.UPDATED) for r in results):
        save_registry(registry, args.registry)
        print(f"\nUpdated {args.registry}")
    return 1 if any(r.status is FetchStatus.FAILED for r in results) else 0


def cmd_check(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    docs = _select(registry, args.doc, include_reserve=False)
    failed = False
    for doc in docs:
        report = check_raw_file(doc, args.raw_dir)
        print(report.summary())
        failed |= not report.ok
    return 1 if failed else 0


def _summary(tree: Document) -> str:
    blocks = [b for _, _, b in walk(tree)]
    by_type = Counter(b.type.value for b in blocks)
    parts = [f"{sum(1 for _ in iter_sections(tree))} sections", f"{len(blocks)} blocks"]
    parts += [f"{t} {n}" for t, n in sorted(by_type.items())]
    if ocr := sum(1 for b in blocks if b.ocr):
        parts.append(f"OCR {ocr}")
    return ", ".join(parts)


def cmd_parse(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    for doc in _select(registry, args.doc, include_reserve=False):
        tree = parse_document(doc, args.raw_dir)
        print(f"== {doc.doc_id}: {_summary(tree)}")
        if args.save:
            saved = save_parsed(tree, doc, args.parsed_dir, args.raw_dir)
            shown = saved.relative_to(PROJECT_ROOT) if saved.is_relative_to(PROJECT_ROOT) else saved
            print(f"saved {shown}")
        if args.dump or args.full:
            print(outline(tree, counts=True))
            tables = [(path, b) for path, _, b in walk(tree) if b.table]
            if tables:
                print(f"\n-- {len(tables)} table(s)")
            for path, b in tables:
                t = b.table
                assert t is not None
                pages = f"p. {b.page}" + (f"-{b.page_end}" if b.page_end else "") if b.page else ""
                print(f"{t.table_id or '-'}  {pages}  {len(t.rows)} rows x {t.n_cols} cols"
                      f"  [{path[-1]}]  {t.caption or ''}")  # fmt: skip
                for row in t.header_rows:
                    print(f"    header: {' | '.join(row)}")
        if args.full:
            print("\n-- blocks")
            for path, _, b in walk(tree):
                page = f"p.{b.page} " if b.page else ""
                print(f"\n[{b.type.value}] {page}{' > '.join(path)}{'  (OCR)' if b.ocr else ''}")
                print(b.text)
        print()
    return 0


def cmd_chunk(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    total = 0
    flagged = 0
    for doc in _select(registry, args.doc, include_reserve=False):
        chunks, report = chunk_document(doc, parsed_dir=args.parsed_dir, raw_dir=args.raw_dir)
        write_chunks(chunks, args.chunks_dir / f"{doc.doc_id}.jsonl")
        write_qc(chunks, report, args.qc_dir)
        sizes = sorted(c.token_count for c in chunks)
        by_type = ", ".join(
            f"{k} {v}" for k, v in sorted(Counter(c.block_type.value for c in chunks).items())
        )
        median = sizes[len(sizes) // 2]
        print(f"== {doc.doc_id}: {len(chunks)} chunks, median {median}, max {sizes[-1]}; {by_type}")
        for table_id, reasons in report.flagged_tables.items():
            print(f"   FLAGGED table {table_id}: {'; '.join(reasons)}")
        total += len(chunks)
        flagged += len(report.flagged_tables)
    print(f"\n{total} chunks written to {args.chunks_dir}; QC reports in {args.qc_dir}")
    return 1 if flagged else 0


def cmd_index(args: argparse.Namespace) -> int:
    embedder = CachedEmbedder(SentenceTransformerEmbedder())
    store = VectorStore(path=args.index_dir, url=os.environ.get("QDRANT_URL"))
    try:
        report = build_index(
            store,
            embedder,
            chunks_dir=args.chunks_dir,
            doc_ids=args.doc or None,
            force=args.force,
            manifest_path=args.index_dir / "manifest.json",
        )
        for doc_id, n in report.indexed.items():
            print(f"indexed  {doc_id:32} {n:4} chunks  ({store.count(doc_id)} points)")
        for doc_id in report.skipped:
            print(f"skipped  {doc_id:32} unchanged ({store.count(doc_id)} points)")
        for doc_id in report.removed:
            print(f"removed  {doc_id}")
        print(
            f"\n{store.count()} points in '{store.collection}' with {report.model}"
            f"{' (rebuilt)' if report.rebuilt else ''}; embedding cache: "
            f"{embedder.hits} hit(s), {embedder.misses} new"
        )
    finally:
        store.close()
        embedder.close()
    return 0


def cmd_vectors(args: argparse.Namespace) -> int:
    from guidance_rag.config import EmbeddingConfig
    from guidance_rag.store import load_chunks

    texts = [c.embed_text for c in load_chunks(args.chunks_dir)]
    written, embedded = export_vectors(
        texts, EmbeddingConfig().model, args.out, make_embedder=SentenceTransformerEmbedder
    )
    shown = (
        args.out.relative_to(PROJECT_ROOT) if args.out.is_relative_to(PROJECT_ROOT) else args.out
    )
    print(f"{written} vectors written to {shown} ({embedded} newly embedded)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m guidance_rag.ingest")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download source documents into corpus/raw/")
    fetch.add_argument("--doc", action="append", default=[], metavar="DOC_ID")
    fetch.add_argument(
        "--refresh", action="store_true", help="re-download to detect changes at the source"
    )
    fetch.add_argument("--include-reserve", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    check = sub.add_parser("check", help="check downloaded files: pages, text layer, title")
    check.add_argument("--doc", action="append", default=[], metavar="DOC_ID")
    check.set_defaults(func=cmd_check)

    parse = sub.add_parser("parse", help="parse raw files into document trees and report")
    parse.add_argument("--doc", action="append", default=[], metavar="DOC_ID")
    parse.add_argument("--dump", action="store_true", help="print each outline and table list")
    parse.add_argument("--full", action="store_true", help="also print every block's text")
    parse.add_argument(
        "--save", action="store_true", help="write each tree to corpus/parsed/{doc_id}.json"
    )
    parse.add_argument("--parsed-dir", type=Path, default=DEFAULT_PARSED_DIR)
    parse.set_defaults(func=cmd_parse)

    chunk = sub.add_parser("chunk", help="chunk parsed trees into corpus/chunks/{doc_id}.jsonl")
    chunk.add_argument("--doc", action="append", default=[], metavar="DOC_ID")
    chunk.add_argument("--parsed-dir", type=Path, default=DEFAULT_PARSED_DIR)
    chunk.add_argument("--chunks-dir", type=Path, default=DEFAULT_CHUNKS_DIR)
    chunk.add_argument("--qc-dir", type=Path, default=DEFAULT_QC_DIR)
    chunk.set_defaults(func=cmd_chunk)

    index = sub.add_parser("index", help="embed chunks and load them into the vector index")
    index.add_argument("--doc", action="append", default=[], metavar="DOC_ID")
    index.add_argument("--chunks-dir", type=Path, default=DEFAULT_CHUNKS_DIR)
    index.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    index.add_argument("--force", action="store_true", help="recreate the collection")
    index.set_defaults(func=cmd_index)

    vectors = sub.add_parser(
        "vectors", help="write the current chunks' vectors to corpus/embeddings.sqlite"
    )
    vectors.add_argument("--chunks-dir", type=Path, default=DEFAULT_CHUNKS_DIR)
    vectors.add_argument("--out", type=Path, default=DEFAULT_VECTORS_FILE)
    vectors.set_defaults(func=cmd_vectors)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
