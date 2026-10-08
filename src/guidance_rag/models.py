"""Core data models shared by ingestion, retrieval, answering and the API.

See ARCHITECTURE.md §3.2 (SourceDocument), §5.3 (Chunk), §6.5 (LLM output shape)
and §10 (API response shape).
"""

import re
from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

# --- Enums -----------------------------------------------------------------


class DocumentStatus(StrEnum):
    INCLUDED = "included"
    RESERVE = "reserve"
    EXCLUDED = "excluded"


class DocumentFormat(StrEnum):
    PDF = "pdf"
    HTML = "html"


class RetrievalMethod(StrEnum):
    DIRECT = "direct"  # downloaded from source_url
    ARCHIVE = "archive"  # source blocks scripts; downloaded from an archived copy (fetch_url)
    MANUAL = "manual"  # saved by hand into corpus/raw/; the fetcher only hashes it


class Domain(StrEnum):
    NUTRITION = "nutrition"
    FOOD_SAFETY = "food_safety"
    ADDITIVES = "additives"


class BlockType(StrEnum):
    PROSE = "prose"
    RECOMMENDATION = "recommendation"
    TABLE = "table"
    LIST = "list"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    NOT_IN_CORPUS = "not_in_corpus"
    OUT_OF_SCOPE = "out_of_scope"


class RefusalCategory(StrEnum):
    # Out of scope by design (§7.2)
    MEDICAL = "medical"
    CALORIE_TARGET = "calorie_target"
    BODY_WEIGHT = "body_weight"
    NUTRIENT_LOOKUP = "nutrient_lookup"
    # Not in the corpus (§6.4)
    NOT_IN_CORPUS = "not_in_corpus"
    UNKNOWN_DOC = "unknown_doc"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Parser config (per document, in registry.yaml) -------------------------


class HeadingSource(StrEnum):
    FONTS = "fonts"  # detect headings from font size, weight and text (HeadingRule)
    TOC = "toc"  # use the PDF's bookmark outline


class TableStrategy(StrEnum):
    LINES = "lines"  # tables drawn with ruling lines (PyMuPDF find_tables, "lines")
    TEXT = "text"  # tables without ruling lines, found by text alignment
    NONE = "none"  # don't look for tables


class HeadingRule(_Model):
    """A PDF line is a heading at `level` when it matches every condition given."""

    level: int = Field(ge=1, le=6)
    min_size: float = Field(gt=0)  # font size range, in points
    max_size: float | None = None  # defaults to min_size + 0.5
    bold: bool | None = None  # None = either
    pattern: str | None = None  # regex the line text must match (re.search)
    # Add one level per extra part of a leading number: "2" -> level, "2.1" -> level + 1.
    nest_by_number: bool = False

    @property
    def size_range(self) -> tuple[float, float]:
        return self.min_size - 0.25, (self.max_size or self.min_size) + 0.25


def _page_ranges(spec: list[int | str]) -> set[int]:
    pages: set[int] = set()
    for item in spec:
        if isinstance(item, int):
            pages.add(item)
        else:
            first, _, last = item.partition("-")
            pages.update(range(int(first), int(last or first) + 1))
    return pages


class ParserConfig(_Model):
    """How to parse one document. Every field has a working default."""

    # --- PDF ---
    # 1-based pages to leave out: cover, contents, blank record templates, etc.
    # Items are page numbers or inclusive ranges such as "1-13".
    skip_pages: list[int | str] = Field(default_factory=list)
    # Pages whose headings are kept but whose other text is dropped: flowcharts,
    # whose box labels make no sense as prose but whose titles give later tables context.
    headings_only_pages: list[int | str] = Field(default_factory=list)
    heading_source: HeadingSource = HeadingSource.FONTS
    headings: list[HeadingRule] = Field(default_factory=list)  # first match wins
    heading_max_chars: int = 120  # longer lines are never headings
    heading_exclude_regex: str | None = None  # lines matching this are never headings
    # A line matching this starts a recommendation block, which runs until the
    # next heading or recommendation (e.g. DGI's "RATIONALE" and "POINTS TO REGISTER").
    recommendation_regex: str | None = None
    table_strategy: TableStrategy = TableStrategy.LINES
    # Non-heading text larger than this is dropped (labels inside infographics).
    max_body_font_size: float | None = None
    # Drop boxed pull quotes that body text wraps around (they repeat the body text).
    drop_pull_quotes: bool = False
    ocr: bool = True  # OCR pages that have no text layer
    # --- Both ---
    # Extra regexes (case-insensitive, matched against headings without their
    # leading number) for sections to drop with all their content. Added to the
    # built-in list: references, contents, glossary, abbreviations, acknowledgements.
    drop_sections: list[str] = Field(default_factory=list)
    # --- HTML ---
    content_selector: str | None = None  # CSS selector of the main content element
    drop_selectors: list[str] = Field(default_factory=list)  # CSS selectors to remove
    # Parsed tables to leave out (by table_id), e.g. an infographic detected as a table.
    drop_tables: list[str] = Field(default_factory=list)
    # Why the settings are what they are (the registry file can't keep YAML comments).
    notes: str | None = None

    @property
    def skip_page_set(self) -> set[int]:
        return _page_ranges(self.skip_pages)

    @property
    def headings_only_page_set(self) -> set[int]:
        return _page_ranges(self.headings_only_pages)

    @model_validator(mode="after")
    def _check(self) -> Self:
        self.skip_page_set, self.headings_only_page_set  # noqa: B018 — validates the range syntax
        patterns = [self.heading_exclude_regex, self.recommendation_regex, *self.drop_sections]
        for rx in [*patterns, *(rule.pattern for rule in self.headings)]:
            if rx:
                try:
                    re.compile(rx)
                except re.error as exc:
                    raise ValueError(f"invalid regex {rx!r}: {exc}") from exc
        return self


# --- Corpus ----------------------------------------------------------------


class SourceDocument(_Model):
    """One entry in corpus/registry.yaml."""

    doc_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    short_name: str
    # How an answer names the document in a sentence ("According to WHO's healthy diet
    # fact sheet, …"). Falls back to the title.
    cite_as: str | None = None
    publisher: str
    # Publication year. Required for included documents; optional for reserve and
    # excluded ones, which are not downloaded, so their year is not checked.
    year: int | None = Field(default=None, ge=1900, le=2100)
    source_url: HttpUrl
    format: DocumentFormat
    domain: Domain
    status: DocumentStatus
    exclusion_reason: str | None = None
    # Names people use for this document; the query analyzer (4.6) matches them.
    aliases: list[str] = Field(default_factory=list)
    # Text that must appear in the downloaded file; proves we saved the real document.
    title_text: str | None = None
    retrieval_method: RetrievalMethod = RetrievalMethod.DIRECT
    # Where to download from when it differs from source_url (e.g. an archived copy).
    # Citations always link to source_url.
    fetch_url: HttpUrl | None = None
    notes: str | None = None
    parser: ParserConfig | None = None  # None = parse with defaults
    # Set by the fetcher; empty until the document is downloaded.
    retrieval_date: date | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @property
    def download_url(self) -> str:
        return str(self.fetch_url or self.source_url)

    @property
    def raw_filename(self) -> str:
        return f"{self.doc_id}.{self.format.value}"

    @model_validator(mode="after")
    def _check_status_fields(self) -> Self:
        if self.status is DocumentStatus.INCLUDED and self.year is None:
            raise ValueError("included documents need a publication year")
        if self.status is not DocumentStatus.INCLUDED and not self.exclusion_reason:
            raise ValueError(f"{self.status} documents need an exclusion_reason")
        if self.retrieval_method is RetrievalMethod.ARCHIVE and self.fetch_url is None:
            raise ValueError("archive retrieval needs a fetch_url")
        return self


class Chunk(_Model):
    """A retrievable unit of a source document (§5.3)."""

    chunk_id: str  # "{doc_id}:{section_slug}:{seq}" — stable across re-runs
    doc_id: str
    doc_title: str
    publisher: str
    year: int
    source_url: HttpUrl
    retrieval_date: date
    section_path: list[str] = Field(min_length=1)
    section_heading: str  # last element of section_path
    # Headings of small sibling sections merged into this chunk (their text is in `text`).
    subsections: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    deep_link: str  # source_url + "#page=N" (PDF) or "#anchor" (HTML)
    block_type: BlockType
    table_id: str | None = None  # for table chunks: the parsed table (see corpus/overrides/)
    domain: Domain
    text: str  # body shown to the LLM
    embed_text: str  # contextual header + body, used for embedding and BM25
    token_count: int = Field(ge=0)
    ocr: bool = False


# --- Retrieval -------------------------------------------------------------


class ScoredChunk(_Model):
    chunk: Chunk
    score: float  # rerank score (0-1); a pool-order score when reranking is off


class DocEvidence(_Model):
    """The selected chunks from one document, in ranking order."""

    doc_id: str
    chunks: list[ScoredChunk] = Field(min_length=1)

    @property
    def best_score(self) -> float:
        return max(sc.score for sc in self.chunks)


class Evidence(_Model):
    """What the retriever returns: chunks grouped by document (§6.3).

    `documents` is the evidence for the answer, in ranking order. `ranked` is the whole
    candidate pool in the final ranking (pool order fused with rerank order) with each
    chunk's rerank score, and `pool` the same chunk IDs in pool order (before
    reranking); both are kept for evaluation and tracing.
    """

    query: str
    docs_searched: list[str]
    documents: list[DocEvidence] = Field(default_factory=list)
    ranked: list[tuple[str, float]] = Field(default_factory=list)  # (chunk_id, score)
    pool: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)

    @property
    def best_score(self) -> float | None:
        """The best score in the pool, evidence or not (for the 7.1 score check)."""
        return max(s for _, s in self.ranked) if self.ranked else None

    @property
    def chunk_ids(self) -> list[str]:
        return [sc.chunk.chunk_id for doc in self.documents for sc in doc.chunks]


# --- Answers ---------------------------------------------------------------


class Claim(_Model):
    """One short factual statement and the chunks that support it."""

    text: str
    chunk_ids: list[str]


class DocAnswer(_Model):
    """All claims from one source document. Claims never mix documents."""

    doc_id: str
    claims: list[Claim]


class Citation(_Model):
    """A rendered citation. Every field is filled from chunk metadata, never by the LLM."""

    n: int = Field(ge=1)
    chunk_id: str
    doc_id: str
    doc_title: str
    publisher: str
    year: int
    section: str
    page: int | None = None
    url: str
    retrieval_date: date


class Sentence(_Model):
    """One sentence of the rendered answer: a claim from one document, with a lead-in
    naming that document where the answer moves to it. Built in code, never by the LLM."""

    text: str
    doc_id: str
    citations: list[int]


class Refusal(_Model):
    category: RefusalCategory
    message: str


class Answer(_Model):
    """What the pipeline returns for every question, including refusals."""

    status: AnswerStatus
    sections: list[DocAnswer] = Field(default_factory=list)
    sentences: list[Sentence] = Field(default_factory=list)  # the answer, in reading order
    citations: list[Citation] = Field(default_factory=list)
    docs_searched: list[str] = Field(default_factory=list)
    refusal: Refusal | None = None
    not_covered: str | None = None
    markdown: str | None = None  # the rendered answer or refusal (§6.7)
    trace_id: str
