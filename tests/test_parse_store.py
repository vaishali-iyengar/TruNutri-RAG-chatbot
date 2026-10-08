"""Saving parsed trees to corpus/parsed/ and reusing them only while current."""

import json
import shutil
from pathlib import Path

import pytest

from guidance_rag.ingest import parse
from guidance_rag.ingest.parse import (
    ParsedFile,
    load_or_parse,
    load_parsed,
    parse_document,
    save_parsed,
)
from guidance_rag.models import ParserConfig, SourceDocument
from guidance_rag.registry import load_registry

FIXTURE = Path(__file__).parent / "fixtures" / "foodsafety_cold_storage.html"


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    raw, parsed, overrides = tmp_path / "raw", tmp_path / "parsed", tmp_path / "overrides"
    raw.mkdir()
    shutil.copy(FIXTURE, raw / "foodsafety-cold-storage.html")
    return raw, parsed, overrides


@pytest.fixture
def doc() -> SourceDocument:
    return load_registry().get("foodsafety-cold-storage")


def test_saved_file_round_trips_to_the_same_tree(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, parsed, overrides = dirs
    tree = parse_document(doc, raw, overrides)
    path = save_parsed(tree, doc, parsed, raw, overrides)

    assert path == parsed / "foodsafety-cold-storage.json"
    assert load_parsed(doc, parsed, raw, overrides) == tree
    record = ParsedFile.model_validate_json(path.read_text(encoding="utf-8"))
    assert record.doc_id == "foodsafety-cold-storage"


def test_saved_json_leaves_out_empty_and_default_fields(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, parsed, overrides = dirs
    path = save_parsed(parse_document(doc, raw, overrides), doc, parsed, raw, overrides)
    data = json.loads(path.read_text(encoding="utf-8"))
    first_block = data["document"]["sections"][0]["blocks"][0]
    assert first_block.keys() == {"type", "text"}  # no page, table, items or ocr


def test_load_parsed_is_none_when_nothing_was_saved(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, parsed, overrides = dirs
    assert load_parsed(doc, parsed, raw, overrides) is None


def test_changed_raw_file_makes_the_saved_tree_stale(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, parsed, overrides = dirs
    save_parsed(parse_document(doc, raw, overrides), doc, parsed, raw, overrides)
    page = raw / "foodsafety-cold-storage.html"
    page.write_text(page.read_text(encoding="utf-8") + "<!-- edited -->", encoding="utf-8")
    assert load_parsed(doc, parsed, raw, overrides) is None


def test_changed_parser_config_makes_the_saved_tree_stale(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, parsed, overrides = dirs
    save_parsed(parse_document(doc, raw, overrides), doc, parsed, raw, overrides)
    changed = doc.model_copy(update={"parser": ParserConfig(content_selector="main")})
    assert load_parsed(changed, parsed, raw, overrides) is None


def test_new_override_makes_the_saved_tree_stale(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, parsed, overrides = dirs
    save_parsed(parse_document(doc, raw, overrides), doc, parsed, raw, overrides)
    (overrides / doc.doc_id).mkdir(parents=True)
    (overrides / doc.doc_id / "foo-bar-baz.csv").write_text("Food,Fridge\nEggs,3 weeks\n")
    assert load_parsed(doc, parsed, raw, overrides) is None


def test_changed_parser_code_makes_the_saved_tree_stale(
    doc: SourceDocument, dirs: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, parsed, overrides = dirs
    save_parsed(parse_document(doc, raw, overrides), doc, parsed, raw, overrides)
    monkeypatch.setattr(parse, "_parser_code_hash", lambda: "different code")
    assert load_parsed(doc, parsed, raw, overrides) is None


def test_load_or_parse_parses_once_then_reuses_the_saved_tree(
    doc: SourceDocument, dirs: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, parsed, overrides = dirs
    first = load_or_parse(doc, parsed, raw, overrides)
    assert (parsed / "foodsafety-cold-storage.json").exists()

    def fail(*args: object) -> None:
        raise AssertionError("should read the saved tree, not parse again")

    monkeypatch.setattr(parse, "parse_document", fail)
    assert load_or_parse(doc, parsed, raw, overrides) == first


def test_drop_tables_removes_listed_tables_and_rejects_unknown_ids(
    doc: SourceDocument, dirs: tuple[Path, Path, Path]
) -> None:
    raw, _, overrides = dirs
    config = (doc.parser or ParserConfig()).model_copy(update={"drop_tables": ["foo-bar-baz"]})
    dropped = parse_document(doc.model_copy(update={"parser": config}), raw, overrides)
    assert not [b for s in dropped.sections for b in s.blocks if b.table]

    unknown = config.model_copy(update={"drop_tables": ["p99-t9"]})
    with pytest.raises(ValueError, match="p99-t9"):
        parse_document(doc.model_copy(update={"parser": unknown}), raw, overrides)
