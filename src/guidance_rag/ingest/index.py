"""Build the vector index from corpus/chunks/ (implementation-plan.md, 4.3).

Each document is indexed on its own: its points are deleted and its current
chunks inserted. A manifest records the hash of each chunk file and the model
used, so a run skips documents whose chunks haven't changed, and a different
model rebuilds the whole collection.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from guidance_rag.ingest.chunker import DEFAULT_CHUNKS_DIR, read_chunks
from guidance_rag.ingest.embed import Embedder
from guidance_rag.ingest.fetch import sha256_file
from guidance_rag.store import DEFAULT_INDEX_DIR, VectorStore

log = logging.getLogger(__name__)


@dataclass
class IndexReport:
    model: str
    indexed: dict[str, int] = field(default_factory=dict)  # doc_id -> chunks written
    skipped: list[str] = field(default_factory=list)  # unchanged since the last run
    removed: list[str] = field(default_factory=list)  # no longer in corpus/chunks/
    rebuilt: bool = False  # the collection was recreated (new model or --force)


def _read_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


def build_index(
    store: VectorStore,
    embedder: Embedder,
    chunks_dir: Path = DEFAULT_CHUNKS_DIR,
    doc_ids: list[str] | None = None,
    force: bool = False,
    manifest_path: Path = DEFAULT_INDEX_DIR / "manifest.json",
) -> IndexReport:
    """Index the chunk files in `chunks_dir` (all, or only `doc_ids`)."""
    manifest = _read_manifest(manifest_path)
    same_model = manifest.get("model") == embedder.name and manifest.get("dim") == embedder.dim
    rebuild = force or not same_model or not store.exists()
    store.ensure_collection(embedder.dim, recreate=rebuild)
    previous = manifest.get("docs")
    known: dict[str, str] = dict(previous) if isinstance(previous, dict) and not rebuild else {}

    files = {p.stem: p for p in sorted(chunks_dir.glob("*.jsonl"))}
    if doc_ids:
        unknown = sorted(set(doc_ids) - set(files))
        if unknown:
            raise ValueError(f"no chunk file for: {unknown}")
        selected = {d: files[d] for d in doc_ids}
    else:
        selected = files

    report = IndexReport(model=embedder.name, rebuilt=rebuild)
    for doc_id, path in selected.items():
        digest = sha256_file(path)
        if known.get(doc_id) == digest and store.count(doc_id) > 0:
            report.skipped.append(doc_id)
            continue
        chunks = read_chunks(path)
        vectors = embedder.embed_documents([c.embed_text for c in chunks])
        store.replace_document(doc_id, chunks, vectors)
        known[doc_id] = digest
        report.indexed[doc_id] = len(chunks)
        log.info("indexed %s: %d chunks", doc_id, len(chunks))

    if not doc_ids:  # a full run also removes documents whose chunk file is gone
        for doc_id in sorted(set(known) - set(files)):
            store.delete_document(doc_id)
            del known[doc_id]
            report.removed.append(doc_id)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"model": embedder.name, "dim": embedder.dim, "docs": known}, indent=1),
        encoding="utf-8",
    )
    return report
