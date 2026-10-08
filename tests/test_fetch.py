from datetime import date
from pathlib import Path

import httpx
import pytest

from guidance_rag.ingest.fetch import (
    FetchError,
    FetchStatus,
    download,
    fetch_all,
    fetch_document,
    sha256_bytes,
)
from guidance_rag.models import SourceDocument

PDF_BYTES = b"%PDF-1.7\n... Dietary Guidelines for Indians ..."
PDF_BYTES_V2 = b"%PDF-1.7\n... Dietary Guidelines for Indians, revised ..."
HTML_BYTES = b"<!DOCTYPE html><html><head><title>Healthy diet</title></head></html>"
TODAY = date(2026, 10, 4)


def make_doc(**update: object) -> SourceDocument:
    data: dict[str, object] = {
        "doc_id": "test-doc",
        "title": "Dietary Guidelines for Indians",
        "short_name": "DGI",
        "publisher": "ICMR – National Institute of Nutrition",
        "year": 2024,
        "source_url": "https://example.org/dgi.pdf",
        "format": "pdf",
        "domain": "nutrition",
        "status": "included",
        "title_text": "Dietary Guidelines for Indians",
    }
    return SourceDocument.model_validate(data | update)


class Server:
    """A fake HTTP server: serves fixed responses and counts requests."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def no_sleep(_: float) -> None:
    pass


def test_first_download_saves_file_and_records_provenance(tmp_path: Path) -> None:
    server = Server(httpx.Response(200, content=PDF_BYTES))

    result = fetch_document(make_doc(), server.client(), raw_dir=tmp_path, today=TODAY)

    assert result.status is FetchStatus.NEW
    assert (tmp_path / "test-doc.pdf").read_bytes() == PDF_BYTES
    assert result.doc.sha256 == sha256_bytes(PDF_BYTES)
    assert result.doc.retrieval_date == TODAY


def test_second_run_downloads_nothing(tmp_path: Path) -> None:
    (tmp_path / "test-doc.pdf").write_bytes(PDF_BYTES)
    doc = make_doc(sha256=sha256_bytes(PDF_BYTES), retrieval_date="2026-01-01")
    server = Server(httpx.Response(500))

    result = fetch_document(doc, server.client(), raw_dir=tmp_path, today=TODAY)

    assert result.status is FetchStatus.SKIPPED
    assert server.requests == []
    assert result.doc == doc


def test_refresh_with_unchanged_content_keeps_retrieval_date(tmp_path: Path) -> None:
    (tmp_path / "test-doc.pdf").write_bytes(PDF_BYTES)
    doc = make_doc(sha256=sha256_bytes(PDF_BYTES), retrieval_date="2026-01-01")
    server = Server(httpx.Response(200, content=PDF_BYTES))

    result = fetch_document(doc, server.client(), raw_dir=tmp_path, refresh=True, today=TODAY)

    assert result.status is FetchStatus.UNCHANGED
    assert len(server.requests) == 1
    assert result.doc.retrieval_date == date(2026, 1, 1)


def test_changed_content_updates_hash_date_and_file(tmp_path: Path) -> None:
    (tmp_path / "test-doc.pdf").write_bytes(PDF_BYTES)
    doc = make_doc(sha256=sha256_bytes(PDF_BYTES), retrieval_date="2026-01-01")
    server = Server(httpx.Response(200, content=PDF_BYTES_V2))

    result = fetch_document(doc, server.client(), raw_dir=tmp_path, refresh=True, today=TODAY)

    assert result.status is FetchStatus.UPDATED
    assert result.doc.sha256 == sha256_bytes(PDF_BYTES_V2)
    assert result.doc.retrieval_date == TODAY
    assert (tmp_path / "test-doc.pdf").read_bytes() == PDF_BYTES_V2


def test_missing_file_is_restored_without_changing_provenance(tmp_path: Path) -> None:
    doc = make_doc(sha256=sha256_bytes(PDF_BYTES), retrieval_date="2026-01-01")
    server = Server(httpx.Response(200, content=PDF_BYTES))

    result = fetch_document(doc, server.client(), raw_dir=tmp_path, today=TODAY)

    assert result.status is FetchStatus.UNCHANGED
    assert (tmp_path / "test-doc.pdf").exists()
    assert result.doc == doc


def test_downloads_from_fetch_url_when_set(tmp_path: Path) -> None:
    doc = make_doc(
        retrieval_method="archive",
        fetch_url="https://web.archive.org/web/2026id_/https://example.org/dgi.pdf",
    )
    server = Server(httpx.Response(200, content=PDF_BYTES))

    fetch_document(doc, server.client(), raw_dir=tmp_path, today=TODAY)

    assert str(server.requests[0].url).startswith("https://web.archive.org/")


@pytest.mark.parametrize(
    ("doc_update", "content", "message"),
    [
        ({}, b"<html>Access Denied</html>", "expected a PDF"),
        ({"format": "html", "title_text": "Healthy diet"}, b"%PDF-1.7", "expected an HTML page"),
        (
            {"format": "html", "title_text": "Healthy diet"},
            b"<html><body>Please accept cookies</body></html>",
            "does not contain 'Healthy diet'",
        ),
    ],
)
def test_wrong_content_is_rejected_and_not_saved(
    tmp_path: Path, doc_update: dict[str, object], content: bytes, message: str
) -> None:
    doc = make_doc(**doc_update)
    server = Server(httpx.Response(200, content=content))

    with pytest.raises(FetchError, match=message):
        fetch_document(doc, server.client(), raw_dir=tmp_path, today=TODAY)
    assert not any(tmp_path.iterdir())


def test_html_document_is_accepted(tmp_path: Path) -> None:
    doc = make_doc(format="html", title_text="Healthy diet")
    server = Server(httpx.Response(200, content=HTML_BYTES))

    result = fetch_document(doc, server.client(), raw_dir=tmp_path, today=TODAY)

    assert result.status is FetchStatus.NEW
    assert result.path.name == "test-doc.html"


def test_download_retries_server_errors() -> None:
    server = Server(httpx.Response(503), httpx.Response(200, content=b"ok"))

    assert download(server.client(), "https://example.org/x", sleep=no_sleep) == b"ok"
    assert len(server.requests) == 2


def test_download_gives_up_after_retries() -> None:
    server = Server(httpx.Response(503))

    with pytest.raises(FetchError, match="giving up"):
        download(server.client(), "https://example.org/x", retries=2, sleep=no_sleep)
    assert len(server.requests) == 3


def test_download_does_not_retry_client_errors() -> None:
    server = Server(httpx.Response(403))

    with pytest.raises(FetchError, match="HTTP 403"):
        download(server.client(), "https://example.org/x", sleep=no_sleep)
    assert len(server.requests) == 1


def test_manual_document_is_hashed_from_disk(tmp_path: Path) -> None:
    (tmp_path / "test-doc.pdf").write_bytes(PDF_BYTES)
    server = Server(httpx.Response(500))

    result = fetch_document(
        make_doc(retrieval_method="manual"), server.client(), raw_dir=tmp_path, today=TODAY
    )

    assert result.status is FetchStatus.NEW
    assert result.doc.sha256 == sha256_bytes(PDF_BYTES)
    assert server.requests == []


def test_manual_document_without_file_fails(tmp_path: Path) -> None:
    server = Server(httpx.Response(500))

    with pytest.raises(FetchError, match="save the file"):
        fetch_document(
            make_doc(retrieval_method="manual"), server.client(), raw_dir=tmp_path, today=TODAY
        )


def test_fetch_all_records_failures_and_continues(tmp_path: Path) -> None:
    good = make_doc(doc_id="good")
    bad = make_doc(doc_id="bad", source_url="https://example.org/missing.pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        if "missing" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=PDF_BYTES)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_all([bad, good], client, raw_dir=tmp_path, today=TODAY, sleep=no_sleep)

    assert [r.status for r in results] == [FetchStatus.FAILED, FetchStatus.NEW]
    assert results[0].error is not None and "HTTP 404" in results[0].error
