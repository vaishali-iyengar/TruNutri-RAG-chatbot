"""Download source documents into corpus/raw/ and record their provenance.

For each document the fetcher:
- skips it without any network call when the raw file is present and matches the
  registry's sha256 (unless `refresh=True`);
- otherwise downloads it, checks it is really a PDF/HTML document (not an error or
  cookie page), saves it, and records sha256 and retrieval_date in the registry.

retrieval_date changes only when the content changes, so it records when this
version of the document was first retrieved.
"""

import hashlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

import httpx

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.models import DocumentFormat, RetrievalMethod, SourceDocument

DEFAULT_RAW_DIR = PROJECT_ROOT / "corpus" / "raw"

# Some government sites reject the default httpx user-agent.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    """A document could not be downloaded or did not look like the expected file."""


class FetchStatus(StrEnum):
    SKIPPED = "skipped"  # raw file present and matches the registry; no download
    NEW = "new"  # first download
    UNCHANGED = "unchanged"  # downloaded again; content same as recorded
    UPDATED = "updated"  # downloaded; content differs from what was recorded
    FAILED = "failed"


@dataclass(frozen=True)
class FetchResult:
    doc: SourceDocument  # the document with updated sha256 / retrieval_date
    status: FetchStatus
    path: Path
    size: int = 0
    error: str | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_content(doc: SourceDocument, content: bytes) -> None:
    """Raise FetchError if the bytes are not the kind of document we expect."""
    if doc.format is DocumentFormat.PDF:
        if not content.startswith(b"%PDF-"):
            raise FetchError(f"{doc.doc_id}: expected a PDF, got {content[:40]!r}")
    else:
        head = content[:4096].lower()
        if b"<html" not in head and b"<!doctype html" not in head:
            raise FetchError(f"{doc.doc_id}: expected an HTML page, got {content[:40]!r}")
    if doc.title_text and doc.format is DocumentFormat.HTML:
        text = content.decode("utf-8", errors="replace").lower()
        if doc.title_text.lower() not in text:
            raise FetchError(
                f"{doc.doc_id}: page does not contain {doc.title_text!r}; "
                "it may be an error, redirect or cookie page"
            )


def download(
    client: httpx.Client,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """GET a URL, retrying on network errors and 429/5xx responses."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        try:
            response = client.get(url)
        except httpx.TransportError as exc:
            last_error = exc
            continue
        if response.status_code in RETRYABLE_STATUS:
            last_error = FetchError(f"HTTP {response.status_code} from {url}")
            continue
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code} from {url}")
        return response.content
    raise FetchError(f"giving up on {url} after {retries + 1} attempts: {last_error}")


def make_client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(headers=BROWSER_HEADERS, timeout=timeout, follow_redirects=True)


def fetch_document(
    doc: SourceDocument,
    client: httpx.Client,
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
    refresh: bool = False,
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    path = raw_dir / doc.raw_filename
    today = today or date.today()

    if doc.retrieval_method is RetrievalMethod.MANUAL:
        if not path.exists():
            raise FetchError(
                f"{doc.doc_id}: retrieval_method is manual; save the file to {path} first"
            )
        content = path.read_bytes()
    else:
        if not refresh and path.exists() and doc.sha256 and sha256_file(path) == doc.sha256:
            return FetchResult(doc, FetchStatus.SKIPPED, path, path.stat().st_size)
        content = download(client, doc.download_url, sleep=sleep)

    check_content(doc, content)
    digest = sha256_bytes(content)

    if doc.sha256 is None:
        status = FetchStatus.NEW
    elif digest == doc.sha256:
        status = FetchStatus.UNCHANGED
    else:
        status = FetchStatus.UPDATED

    if status is not FetchStatus.UNCHANGED or not path.exists():
        raw_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(content)
        tmp.replace(path)

    if status is not FetchStatus.UNCHANGED:
        doc = doc.model_copy(update={"sha256": digest, "retrieval_date": today})
    return FetchResult(doc, status, path, len(content))


def fetch_all(
    docs: Iterable[SourceDocument],
    client: httpx.Client,
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
    refresh: bool = False,
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[FetchResult]:
    """Fetch each document. A failure is recorded and does not stop the others."""
    results = []
    for doc in docs:
        try:
            result = fetch_document(
                doc, client, raw_dir=raw_dir, refresh=refresh, today=today, sleep=sleep
            )
        except FetchError as exc:
            result = FetchResult(
                doc, FetchStatus.FAILED, raw_dir / doc.raw_filename, error=str(exc)
            )
        results.append(result)
    return results
