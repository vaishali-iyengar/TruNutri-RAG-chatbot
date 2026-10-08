"""Parse a registry document's raw file into a document tree, and store it as JSON.

Parsed trees are saved to `corpus/parsed/{doc_id}.json` with a fingerprint of
everything that produced them: the raw file, the document's parser config, its
table overrides and the parser code. `load_or_parse()` uses the saved file only
while the fingerprint still matches, so a stale tree is never read.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.ingest import overrides, parse_html, parse_pdf, text, tree
from guidance_rag.ingest.fetch import DEFAULT_RAW_DIR, sha256_file
from guidance_rag.ingest.overrides import DEFAULT_OVERRIDES_DIR, apply_overrides
from guidance_rag.ingest.tree import Document
from guidance_rag.models import DocumentFormat, SourceDocument

DEFAULT_PARSED_DIR = PROJECT_ROOT / "corpus" / "parsed"

# Modules whose code decides the parsed output; editing any of them invalidates saved trees.
_PARSER_MODULES = [parse_pdf, parse_html, tree, text, overrides]


class ParsedFile(BaseModel):
    """What `corpus/parsed/{doc_id}.json` holds."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    source_sha256: str  # hash of the raw file that was parsed
    fingerprint: str  # raw file + parser config + overrides + parser code
    document: Document


def _parser_code_hash() -> str:
    h = hashlib.sha256()
    for module_file in [*(m.__file__ for m in _PARSER_MODULES), __file__]:  # and this module
        h.update(Path(str(module_file)).read_bytes())
    return h.hexdigest()


def fingerprint(
    doc: SourceDocument,
    raw_dir: Path = DEFAULT_RAW_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
) -> str:
    """Hash of everything that determines the parsed tree for `doc`."""
    parts = {
        "source": sha256_file(raw_dir / doc.raw_filename),
        "title": doc.title,
        "config": doc.parser.model_dump(mode="json") if doc.parser else None,
        "overrides": {
            p.name: sha256_file(p) for p in sorted((overrides_dir / doc.doc_id).glob("*.csv"))
        },
        "code": _parser_code_hash(),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def parse_document(
    doc: SourceDocument,
    raw_dir: Path = DEFAULT_RAW_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
) -> Document:
    path = raw_dir / doc.raw_filename
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run `python -m guidance_rag.ingest fetch`")
    if doc.format is DocumentFormat.PDF:
        parsed = parse_pdf.parse_pdf(path, doc_id=doc.doc_id, title=doc.title, config=doc.parser)
    else:
        html = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_html.parse_html(html, doc_id=doc.doc_id, title=doc.title, config=doc.parser)
    apply_overrides(parsed, overrides_dir)
    if doc.parser and doc.parser.drop_tables:
        drop_tables(parsed, doc.parser.drop_tables)
    return parsed


def drop_tables(document: Document, table_ids: list[str]) -> None:
    """Remove the listed tables. Every id must match a parsed table."""
    found = set()
    for _, section in tree.iter_sections(document):
        kept = []
        for block in section.blocks:
            if block.table and block.table.table_id in table_ids:
                found.add(block.table.table_id)
            else:
                kept.append(block)
        section.blocks = kept
    missing = sorted(set(table_ids) - found)
    if missing:
        raise ValueError(f"{document.doc_id}: drop_tables lists unknown table(s): {missing}")


def read_saved(doc_id: str, parsed_dir: Path = DEFAULT_PARSED_DIR) -> Document | None:
    """The saved tree as it is, without checking that it is current.

    For checks that must run without the raw files (e.g. in CI); use
    `load_or_parse()` everywhere else.
    """
    path = parsed_dir / f"{doc_id}.json"
    if not path.exists():
        return None
    return ParsedFile.model_validate_json(path.read_text(encoding="utf-8")).document


def save_parsed(
    document: Document,
    doc: SourceDocument,
    parsed_dir: Path = DEFAULT_PARSED_DIR,
    raw_dir: Path = DEFAULT_RAW_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
) -> Path:
    """Write the tree as indented JSON. Empty and default fields are left out."""
    record = ParsedFile(
        doc_id=doc.doc_id,
        source_sha256=sha256_file(raw_dir / doc.raw_filename),
        fingerprint=fingerprint(doc, raw_dir, overrides_dir),
        document=document,
    )
    parsed_dir.mkdir(parents=True, exist_ok=True)
    path = parsed_dir / f"{doc.doc_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(record.model_dump_json(indent=1, exclude_defaults=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_parsed(
    doc: SourceDocument,
    parsed_dir: Path = DEFAULT_PARSED_DIR,
    raw_dir: Path = DEFAULT_RAW_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
) -> Document | None:
    """The saved tree, or None if there is none or it is out of date."""
    path = parsed_dir / f"{doc.doc_id}.json"
    if not path.exists() or not (raw_dir / doc.raw_filename).exists():
        return None
    record = ParsedFile.model_validate_json(path.read_text(encoding="utf-8"))
    if record.fingerprint != fingerprint(doc, raw_dir, overrides_dir):
        return None
    return record.document


def load_or_parse(
    doc: SourceDocument,
    parsed_dir: Path = DEFAULT_PARSED_DIR,
    raw_dir: Path = DEFAULT_RAW_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
) -> Document:
    """The saved tree if it is current; otherwise parse, save and return it."""
    document = load_parsed(doc, parsed_dir, raw_dir, overrides_dir)
    if document is None:
        document = parse_document(doc, raw_dir, overrides_dir)
        save_parsed(document, doc, parsed_dir, raw_dir, overrides_dir)
    return document
