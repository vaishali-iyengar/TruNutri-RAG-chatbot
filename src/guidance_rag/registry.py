"""Load and save corpus/registry.yaml: the single source of truth for source documents."""

from collections.abc import Iterator
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.models import DocumentStatus, SourceDocument

DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "corpus" / "registry.yaml"

_HEADER = """\
# Corpus registry — source documents and their provenance (ARCHITECTURE.md §3).
#
# Edit by hand to add or change documents. `retrieval_date` and `sha256` are
# written by the fetcher (`python -m guidance_rag.ingest fetch`), which rewrites
# this file, so put explanations in `notes` rather than in YAML comments.

"""


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[SourceDocument]

    @model_validator(mode="after")
    def _unique_doc_ids(self) -> Self:
        ids = [d.doc_id for d in self.documents]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate doc_ids in registry: {duplicates}")
        return self

    def __iter__(self) -> Iterator[SourceDocument]:  # type: ignore[override]
        return iter(self.documents)

    def get(self, doc_id: str) -> SourceDocument:
        for doc in self.documents:
            if doc.doc_id == doc_id:
                return doc
        raise KeyError(f"unknown doc_id: {doc_id!r}")

    def with_status(self, *statuses: DocumentStatus) -> list[SourceDocument]:
        return [d for d in self.documents if d.status in statuses]

    @property
    def included(self) -> list[SourceDocument]:
        return self.with_status(DocumentStatus.INCLUDED)

    def replace(self, doc: SourceDocument) -> None:
        """Swap in an updated copy of a document, keeping its position."""
        for i, existing in enumerate(self.documents):
            if existing.doc_id == doc.doc_id:
                self.documents[i] = doc
                return
        raise KeyError(f"unknown doc_id: {doc.doc_id!r}")


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> Registry:
    with path.open(encoding="utf-8") as f:
        return Registry.model_validate(yaml.safe_load(f))


def save_registry(registry: Registry, path: Path = DEFAULT_REGISTRY_PATH) -> None:
    data = registry.model_dump(mode="json", exclude_none=True, exclude_defaults=False)
    # Keep hand-written parser config short: write only the settings that differ from defaults.
    for entry, doc in zip(data["documents"], registry.documents, strict=True):
        if doc.parser is not None:
            entry["parser"] = doc.parser.model_dump(mode="json", exclude_defaults=True)
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(_HEADER + body, encoding="utf-8")
    tmp.replace(path)
