# TruNutri RAG Chatbot

A chatbot that answers questions about food, nutrition and food safety **only** from official public guidance documents. Every claim carries a citation. When the guidance doesn't cover a question, the assistant says so.

- Problem statement: [problem-statement.md](problem-statement.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Implementation plan: [implementation-plan.md](implementation-plan.md)

> Work in progress. The full README (corpus, chunking choices and their cost, evaluation results) is written in Phase 10 of the implementation plan.

## Development setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 automatically.

```bash
uv sync --extra ocr --extra embed   # dependencies; OCR and the embedding model are optional extras
cp .env.example .env          # then fill in GROQ_API_KEY (LLM calls run on Groq)
uv run pre-commit install     # optional: run checks before each commit

uv run pytest                 # tests (corpus tests skip until the corpus is fetched)
uv run pytest -m "not corpus" # skip the slower tests that parse the real corpus
uv run ruff check .           # lint
uv run ruff format --check .  # formatting
uv run mypy                   # type check
```

### Keep the virtual environment out of iCloud

If the project lives in an iCloud-synced folder (Desktop or Documents with iCloud Drive), don't keep `.venv` inside it. iCloud marks the files as hidden, which makes Python 3.12 skip the editable-install `.pth` file (`ModuleNotFoundError: No module named 'guidance_rag'`), and "Optimize Mac Storage" can make reads block, so tools hang. Put the environment outside iCloud and link to it:

```bash
rm -rf .venv
uv venv --python 3.12 ~/.venvs/guidance-rag
ln -s ~/.venvs/guidance-rag .venv
uv sync
```

## Corpus

Source documents and their provenance are listed in [corpus/registry.yaml](corpus/registry.yaml). Downloaded files go to `corpus/raw/` (not committed; re-create them with the fetcher).

```bash
uv run python -m guidance_rag.ingest fetch             # download included documents (skips ones already present)
uv run python -m guidance_rag.ingest fetch --refresh   # re-download to detect changes at the source
uv run python -m guidance_rag.ingest check             # pages, text layer and title check per file
```

### Parsing

Each raw file is parsed into a document tree: nested sections, each holding typed blocks (paragraph, list, table or numbered recommendation) with page numbers. Only text, structure and pages are kept; cover pages, contents, reference lists, blank record templates and personalised meal plans are left out. Per-document settings (pages to skip, heading rules) live in the `parser` entry of each document in the registry, with a `notes` line explaining them.

```bash
uv run python -m guidance_rag.ingest parse                       # one summary line per document
uv run python -m guidance_rag.ingest parse --dump --doc DOC_ID   # outline, block counts and tables
uv run python -m guidance_rag.ingest parse --full --doc DOC_ID   # also every block's text, for review
uv run python -m guidance_rag.ingest parse --save                # write corpus/parsed/{doc_id}.json
```

Saved trees in `corpus/parsed/` are JSON: the document's sections, each with its heading, level, page and blocks. Each file carries a fingerprint of the raw file, the parser config, the table overrides and the parser code. Later stages call `load_or_parse()`, which uses a saved tree only while that fingerprint matches and re-parses otherwise. The files are small (about 2 MB in total) and meant to be committed, so a parser change shows up as a diff.

- **OCR.** Scanned pages (FSSAI Milk pp. 74-75) are read with RapidOCR, installed by `uv sync --extra ocr`. Without it, those pages are skipped with a warning.
- **Table corrections.** When a table is parsed wrongly, save the right version as `corpus/overrides/{doc_id}/{table_id}.csv` (first row = header). The `table_id` is shown by `parse --dump`.

### Chunking

Parsed trees are split into chunks with **structure-aware chunking**: boundaries follow sections, paragraphs, list items and table rows, never a fixed token count. Each recommendation is one chunk; tables stay whole up to 800 tokens and otherwise split between rows (never inside a food category) with the caption and header repeated. Details and limits: Phase 3 of [implementation-plan.md](implementation-plan.md).

```bash
uv run python -m guidance_rag.ingest chunk     # writes corpus/chunks/{doc_id}.jsonl and corpus/qc/{doc_id}.md
```

The corpus gives 903 chunks (median 261 tokens). Each line of a chunk file is one chunk with its document, publisher, year, section path, pages, deep link, the body (`text`) and the text used for search (`embed_text`, the body behind a `[Publisher · Title · Year] [Section: …]` header). The QC report per document lists sizes, split tables and any table that looks broken.

### Indexing

Chunks are embedded with `Alibaba-NLP/gte-modernbert-base` (chosen by a benchmark on the golden set; see Phase 4 of the plan) and stored in a local Qdrant index. Needs `uv sync --extra embed`; the first run downloads the model (~0.6 GB).

```bash
uv run python -m guidance_rag.ingest index            # embed changed chunks and update the index
uv run python -m guidance_rag.ingest index --force    # rebuild the collection from scratch
```

| File | Contents |
|---|---|
| `.index/` | Qdrant collection `guidance_chunks` (one point per chunk, the chunk as payload) and `manifest.json` (model and chunk-file hashes; unchanged documents are skipped) |
| `.cache/embeddings/vectors.sqlite` | Chunk vectors keyed by model + text, so re-indexing only embeds changed chunks |

Both are git-ignored and can be rebuilt from `corpus/chunks/`. Set `QDRANT_URL` to use a Qdrant server instead of the local folder. The keyword (BM25) index has no file: it is built in memory from `corpus/chunks/` in about 0.2 s.
