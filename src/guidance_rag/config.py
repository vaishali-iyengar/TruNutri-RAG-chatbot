"""Application settings, read from environment variables and the project `.env` file.

Use `get_settings()` rather than constructing `Settings()` directly: it turns a
missing API key into a clear `ConfigError` instead of a raw validation error.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secrets -----------------------------------------------------------
    # LLM calls go to Groq (https://console.groq.com/keys).
    groq_api_key: SecretStr

    # --- Paths -------------------------------------------------------------
    corpus_dir: Path = PROJECT_ROOT / "corpus"
    registry_path: Path = PROJECT_ROOT / "corpus" / "registry.yaml"

    # --- Index -------------------------------------------------------------
    # Local Qdrant storage path. Set qdrant_url instead to use a Qdrant server.
    index_path: Path = PROJECT_ROOT / ".index"
    qdrant_url: str | None = None
    collection_name: str = "guidance_chunks"

    # --- Models ------------------------------------------------------------
    embedding_model: str = "Alibaba-NLP/gte-modernbert-base"  # see EmbeddingConfig
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"  # see RetrievalConfig
    # Groq models. These two support strict structured outputs (guaranteed-valid JSON),
    # which the generator (6.3), evidence check (7.2) and scope classifier (5.7) rely on.
    generator_model: str = "openai/gpt-oss-120b"
    evidence_check_model: str = "openai/gpt-oss-20b"

    # --- Groq quotas (rate_limit.py), applied per model ----------------------
    # Free tier for openai/gpt-oss-120b. Tokens per minute count prompt + max completion.
    groq_rpm: int = Field(default=30, ge=1)
    groq_rpd: int = Field(default=1_000, ge=1)
    groq_tpm: int = Field(default=8_000, ge=1)
    groq_tpd: int = Field(default=200_000, ge=1)

    # --- Scope classifier (5.7): optional LLM check after the rules ---------
    # It can only add refusals; the rules stay authoritative. On (decided 2026-10-06): the
    # rules alone catch ~60% of unseen out-of-scope wordings. SCOPE_CLASSIFIER=false turns it off.
    scope_classifier: bool = True
    scope_classifier_model: str = "openai/gpt-oss-20b"
    # Refusals the rules missed, one JSON object per line, for improving the rules.
    scope_classifier_log: Path | None = PROJECT_ROOT / "logs" / "scope_classifier.jsonl"

    # --- Answer threshold (score check, 7.1) ---------------------------------
    # The best rerank score must reach this. Calibrated in 7.5 (eval/results/thresholds.md):
    # not-in-corpus golden questions score at most 0.102, answerable ones at least 0.446;
    # 0.27 is the middle of that gap. tau_doc, which the retriever needs, is in
    # RetrievalConfig.
    tau_answer: float = Field(default=0.27, ge=0.0, le=1.0)

    # --- API limits (9.5) ----------------------------------------------------
    # A /chat request that can't finish in this many seconds (e.g. waiting on the Groq
    # quota) fails with 503 instead of hanging.
    chat_timeout_s: float = Field(default=60.0, gt=0)
    # /chat requests allowed per client IP per minute; more get 429.
    chat_rate_per_minute: int = Field(default=20, ge=1)

    @field_validator("groq_api_key")
    @classmethod
    def _key_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("GROQ_API_KEY is empty: paste your Groq API key into .env")
        return value


class ChunkingConfig(BaseModel):
    """Size limits for the chunker (implementation-plan.md, Phase 3), in cl100k tokens.

    Chosen from the parsed corpus: paragraphs have a median of 34 tokens and a
    maximum of 365, recommendations a maximum of 774, and 79 of 103 tables fit
    in 800 tokens. Kept apart from `Settings` so chunking needs no API key.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prose_max: int = 400  # paragraphs and lists packed per section; long lists split here
    table_whole_max: int = 800  # tables up to this size stay whole
    table_group_max: int = 600  # larger tables split into row groups of this size
    small_section_max: int = 120  # sibling sections smaller than this are merged
    recommendation_max: int = 1000  # safety net; no recommendation in the corpus reaches it
    overlap_max: int = 133  # a paragraph is repeated as overlap only if it is this small
    wide_table_columns: int = 6  # wider tables are written one "column: value" line per row
    broken_cell_max: int = 300  # a table cell larger than this marks the table as broken


class EmbeddingConfig(BaseModel):
    """Embedding model for indexing and queries (implementation-plan.md, 4.2).

    gte-modernbert-base won a benchmark on our 903 chunks and the golden set
    (Recall@10 0.93, MRR 0.82, dense only), and its 8k window cuts off no chunk
    (512-token models cut 106). bge-m3 was not tested for lack of disk space; to try
    it, set `model` and `max_seq_length` and re-index.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = "Alibaba-NLP/gte-modernbert-base"
    max_seq_length: int = 1024  # longest embed_text is ~830 tokens
    query_prefix: str = ""  # some models want e.g. "search_query: "
    document_prefix: str = ""
    batch_size: int = 8
    cache_dir: Path = PROJECT_ROOT / ".cache" / "embeddings"


class RetrievalConfig(BaseModel):
    """Hybrid retrieval, reranking and evidence selection (implementation-plan.md, 4.5-4.6).

    Sizes come from the built index and the golden set: the global fused top 30 plus
    each document's top 3 held a gold chunk for all 27 answerable questions (median
    pool 45). Kept apart from `Settings` so retrieval needs no API key.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # --- Candidate pool (4.5) ---
    dense: bool = True  # turn off for the eval's --bm25-only
    bm25: bool = True  # turn off for the eval's --dense-only
    search_k: int = Field(default=40, ge=1)  # hits per dense or BM25 search
    rrf_k: int = Field(default=60, ge=1)  # Reciprocal Rank Fusion constant
    global_k: int = Field(default=30, ge=1)  # fused hits kept from the corpus-wide search
    per_doc_k: int = Field(default=3, ge=0)  # fused hits kept from each document; 0 = off
    table_expand: int = Field(default=8, ge=0)  # sibling pieces of a pooled table added
    # Table rows matched per query (store.TableRowIndex); their tables join the pool and the
    # matching row is reranked too. Added 2026-10-08 for nutrient questions; 0 = off.
    row_k: int = Field(default=5, ge=0)
    # Chunks per table_id in the evidence. 3 since 9.3: with 2, cd-02 lost the row that
    # answers it (fresh poultry, 1-2 days) to two other pieces of the same chart.
    table_cap: int = Field(default=3, ge=1)
    dup_cosine: float = Field(default=0.97, gt=0.0, le=1.0)  # drop near-copies above this

    # --- Rerank (4.6) ---
    rerank: bool = True  # off: keep the pool order (the eval's --no-rerank)
    # Chosen in 4.9 for an 8 GB laptop: 0.7 s per question (bge-reranker-v2-m3: 31 s) with
    # as good recall, and unanswerable questions still score low. It reads 512 tokens;
    # longer chunks are scored in windows (rerank.py).
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    rerank_max_length: int = 1024  # capped at what the model supports
    rerank_batch_size: int = 8

    # --- Evidence selection (4.6) ---
    # Minimum rerank score (sigmoid, 0-1) for a document to be evidence; ignored when rerank
    # is off. From the 4.9 sweep (eval/results/retrieval.md): unanswerable questions score
    # at most 0.10 and answerable ones at least 0.45, so 0.2 keeps the first group empty.
    tau_doc: float = Field(default=0.2, ge=0.0, le=1.0)
    # Once one document passes tau_doc, other documents qualify at this lower score, so a
    # cross-document question keeps its second voice (cd-01's WHO chunk scores 0.11).
    # Unanswerable questions stay empty, since nothing passes tau_doc. Recheck in Phase 7.
    tau_doc_extra: float = Field(default=0.1, ge=0.0, le=1.0)
    per_doc_max: int = Field(default=3, ge=1)  # chunks per document when several qualify
    single_doc_max: int = Field(default=6, ge=1)  # chunks when only one document qualifies
    max_chunks: int = Field(default=8, ge=1)
    # 3 since 9.3 (was 4): a weak fourth document (one off-topic chunk) took a slot from a
    # better chunk of a document that answers. No golden question expects more than 2.
    max_docs: int = Field(default=3, ge=1)


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Build settings from the environment and `env_file` (None = environment only).

    Raises ConfigError with a readable message when a setting is missing or invalid.
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        missing = [str(err["loc"][0]).upper() for err in exc.errors() if err["type"] == "missing"]
        if missing:
            raise ConfigError(
                f"Missing required setting(s): {', '.join(missing)}. "
                "Copy .env.example to .env and fill them in, or set them as environment variables."
            ) from exc
        raise ConfigError(f"Invalid settings: {exc}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process from the project `.env` and the environment."""
    return load_settings()
