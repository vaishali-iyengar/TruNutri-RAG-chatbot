"""Sanity checks on downloaded raw files (sub-task 1.5).

Confirms each file opens, finds pages with no text layer (candidates for OCR in
Phase 2), and checks the document's `title_text` appears near the start.
"""

import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

import pymupdf

from guidance_rag.ingest.fetch import sha256_file
from guidance_rag.models import DocumentFormat, SourceDocument

# A page with fewer extractable characters than this is treated as having no text layer.
MIN_PAGE_CHARS = 25
# Look for the title on the first few pages only (cover / title page).
TITLE_PAGES = 5


@dataclass
class CheckReport:
    doc_id: str
    path: Path
    exists: bool = False
    hash_matches: bool = False
    pages: int | None = None
    pages_without_text: list[int] = field(default_factory=list)
    tables: int | None = None
    title_found: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and self.hash_matches and self.title_found and not self.errors

    def summary(self) -> str:
        if not self.exists:
            return f"MISSING  {self.doc_id:<32} {self.path}"
        parts = []
        if self.pages is not None:
            parts.append(f"{self.pages} pages")
            no_text = self.pages_without_text
            parts.append(
                f"no text layer on {len(no_text)} page(s): {_ranges(no_text)}"
                if no_text
                else "text layer on every page"
            )
        if self.tables is not None:
            parts.append(f"{self.tables} table(s)")
        parts.append("title found" if self.title_found else "TITLE NOT FOUND")
        parts.append("hash ok" if self.hash_matches else "HASH MISMATCH")
        parts.extend(self.errors)
        return f"{'ok' if self.ok else 'PROBLEM':<8} {self.doc_id:<32} " + "; ".join(parts)


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _ranges(pages: list[int]) -> str:
    """[1, 2, 3, 7] -> '1-3, 7' (1-based page numbers)."""
    groups: list[list[int]] = []
    for p in pages:
        if groups and p == groups[-1][1] + 1:
            groups[-1][1] = p
        else:
            groups.append([p, p])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in groups)


def check_raw_file(doc: SourceDocument, raw_dir: Path) -> CheckReport:
    path = raw_dir / doc.raw_filename
    report = CheckReport(doc.doc_id, path)
    if not path.exists():
        return report
    report.exists = True
    report.hash_matches = doc.sha256 is not None and sha256_file(path) == doc.sha256
    title = _normalise(doc.title_text or doc.title)

    try:
        if doc.format is DocumentFormat.PDF:
            with pymupdf.open(path) as pdf:  # type: ignore[no-untyped-call]
                report.pages = pdf.page_count
                first_pages = []
                for i, page in enumerate(pdf):
                    text = page.get_text()
                    if len(text.strip()) < MIN_PAGE_CHARS:
                        report.pages_without_text.append(i + 1)
                    if i < TITLE_PAGES:
                        first_pages.append(text)
                report.title_found = title in _normalise(" ".join(first_pages))
        else:
            html = path.read_text(encoding="utf-8", errors="replace")
            report.tables = len(re.findall(r"<table\b", html, flags=re.IGNORECASE))
            text = unescape(re.sub(r"<[^>]+>", " ", html))
            report.title_found = title in _normalise(text)
    except Exception as exc:  # a corrupt file should be reported, not crash the check
        report.errors.append(f"cannot open: {exc}")
    return report
