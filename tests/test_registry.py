from pathlib import Path

import pytest
from pydantic import ValidationError

from guidance_rag.ingest.check import check_raw_file
from guidance_rag.ingest.fetch import DEFAULT_RAW_DIR
from guidance_rag.models import (
    DocumentFormat,
    DocumentStatus,
    HeadingSource,
    RetrievalMethod,
    SourceDocument,
)
from guidance_rag.registry import Registry, load_registry, save_registry

REGISTRY = load_registry()


def test_registry_loads_with_unique_doc_ids() -> None:
    ids = [d.doc_id for d in REGISTRY]
    assert len(ids) == len(set(ids))


def test_corpus_has_five_to_seven_included_documents() -> None:
    # The brief asks for 5 to 7 public guidance documents.
    assert 5 <= len(REGISTRY.included) <= 7


@pytest.mark.parametrize("doc", REGISTRY.included, ids=lambda d: d.doc_id)
def test_included_documents_have_full_provenance(doc: SourceDocument) -> None:
    assert doc.publisher
    assert doc.year is not None
    assert doc.source_url
    assert doc.retrieval_date is not None, "run: python -m guidance_rag.ingest fetch"
    assert doc.sha256 is not None, "run: python -m guidance_rag.ingest fetch"
    assert doc.title_text, "needed to check the download is the real document"
    assert doc.aliases, "needed by the query analyzer"


@pytest.mark.parametrize(
    "doc",
    REGISTRY.with_status(DocumentStatus.RESERVE, DocumentStatus.EXCLUDED),
    ids=lambda d: d.doc_id,
)
def test_reserve_and_excluded_documents_say_why(doc: SourceDocument) -> None:
    assert doc.exclusion_reason


def test_nutrient_data_sources_are_excluded() -> None:
    # The brief puts nutrient numbers for individual foods in Milestone 3.
    for doc_id in ("efsa-food-composition", "health-canada-cnf"):
        assert REGISTRY.get(doc_id).status is DocumentStatus.EXCLUDED


def test_archived_documents_still_cite_the_original_url() -> None:
    doc = REGISTRY.get("foodsafety-cold-storage")
    assert doc.retrieval_method is RetrievalMethod.ARCHIVE
    assert "web.archive.org" in doc.download_url
    assert str(doc.source_url).startswith("https://www.foodsafety.gov/")


def test_get_unknown_doc_id_raises() -> None:
    with pytest.raises(KeyError):
        REGISTRY.get("nhs-eatwell")


def test_duplicate_doc_ids_are_rejected() -> None:
    doc = REGISTRY.included[0]
    with pytest.raises(ValidationError, match="duplicate doc_ids"):
        Registry(documents=[doc, doc])


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "registry.yaml"
    save_registry(REGISTRY, path)

    assert load_registry(path) == REGISTRY
    assert path.read_text(encoding="utf-8").startswith("# Corpus registry")


def test_saved_parser_config_lists_only_non_default_settings(tmp_path: Path) -> None:
    path = tmp_path / "registry.yaml"
    save_registry(REGISTRY, path)
    text = path.read_text(encoding="utf-8")
    assert "table_strategy: lines" not in text  # the default
    assert "table_strategy: none" in text  # JECFA's setting


@pytest.mark.parametrize("doc", REGISTRY.included, ids=lambda d: d.doc_id)
def test_included_documents_have_parser_config(doc: SourceDocument) -> None:
    assert doc.parser is not None
    if doc.format is DocumentFormat.HTML:
        assert doc.parser.content_selector
    else:
        assert doc.parser.skip_pages, "leave out the cover, contents and other front matter"
        assert doc.parser.headings or doc.parser.heading_source is HeadingSource.TOC


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"status": "reserve"}, "need an exclusion_reason"),
        ({"year": None}, "need a publication year"),
        ({"retrieval_method": "archive", "fetch_url": None}, "needs a fetch_url"),
    ],
)
def test_source_document_rules(update: dict[str, object], message: str) -> None:
    data = REGISTRY.get("icmr-nin-dgi-2024").model_dump(mode="json") | update
    with pytest.raises(ValidationError, match=message):
        SourceDocument.model_validate(data)


# --- Downloaded files (corpus/raw/ is not committed; skipped when absent) ------


@pytest.mark.parametrize("doc", REGISTRY.included, ids=lambda d: d.doc_id)
def test_raw_file_is_the_real_document(doc: SourceDocument) -> None:
    if not (DEFAULT_RAW_DIR / doc.raw_filename).exists():
        pytest.skip("raw file not downloaded; run: python -m guidance_rag.ingest fetch")

    report = check_raw_file(doc, DEFAULT_RAW_DIR)

    assert report.hash_matches, "file differs from the registry; re-run fetch --refresh"
    assert report.title_found, f"{doc.title_text!r} not found near the start of the file"
    assert not report.errors
