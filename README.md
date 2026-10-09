# TruNutri RAG Chatbot

A chatbot that answers questions about food, nutrition and food safety **only** from seven official guidance documents (ICMR-NIN, WHO, FSSAI, FoodSafety.gov, JECFA). Every statement carries a citation: document, publisher, year, section, page and link. When the documents don't cover a question, it says so and names what it searched. Medical advice, personal calorie targets and body-weight goals are refused in code, before any search or language model runs.

**Live:** https://trunutri-1086585845539.us-central1.run.app (Google Cloud Run; the first question after a quiet period takes 20–40 s while it starts)

Docs: [problem statement](problem-statement.md) · [architecture](ARCHITECTURE.md) · [implementation plan](implementation-plan.md) (build log, decisions, measurements) · [deployment](deployment-plan.md)

## Tech stack

| Layer | Choice | Deploy target |
| --- | --- | --- |
| Frontend | One static HTML page (vanilla JS, CSS), served by the backend | [Google Cloud Run](https://cloud.google.com/run) (same container) |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/), Python 3.12, [Pydantic](https://docs.pydantic.dev/) | [Google Cloud Run](https://cloud.google.com/run), key in [Secret Manager](https://cloud.google.com/security/products/secret-manager) |
| Retrieval | [Qdrant](https://qdrant.tech/) (local mode) + [rank_bm25](https://github.com/dorianbrown/rank_bm25), [sentence-transformers](https://sbert.net/): `gte-modernbert-base` embeddings, `ms-marco-MiniLM-L-12-v2` reranker | Baked into the container image |
| Model | [Groq](https://groq.com/) (`groq` SDK): `openai/gpt-oss-120b` for answers, `openai/gpt-oss-20b` for checks | Groq-hosted inference API |
| Ingestion | [PyMuPDF](https://pymupdf.readthedocs.io/), [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/), [RapidOCR](https://github.com/RapidAI/RapidOCR), [tiktoken](https://github.com/openai/tiktoken) | Offline (`make ingest`); output committed |
| Tooling | [uv](https://docs.astral.sh/uv/), [ruff](https://docs.astral.sh/ruff/), [mypy](https://mypy-lang.org/), [pytest](https://pytest.org/), [Docker](https://www.docker.com/), [GitHub Actions](https://github.com/features/actions) | — |

**Frontend:** one chat page with three columns. The left shows the session's questions and the guidance library, the middle is the chat, and the right shows the cited evidence for the selected answer. It has a light/dark toggle and a "search only in" picker. It calls the API on the same origin, so it needs no separate hosting or CORS.

**Backend:** a small REST API (`POST /chat`, `GET /documents`, `GET /health`) that owns the whole pipeline. It runs the scope rules, retrieval, the sufficiency gate, generation, the citation validator and the renderer. It also enforces a per-visitor rate limit and a time limit, and writes a trace for every request.

**Retrieval:** hybrid dense + BM25 search (plus table rows), fused with RRF and reranked by a cross-encoder. The index and both models are built into the image, so a cold start needs no download.

**Model:** strict structured outputs (JSON schema), so the model returns claims with chunk IDs, never links or titles; citations are filled in by code. The smaller model runs the scope classifier and the "does this evidence answer it?" check.

## Quick start

You need a [Groq API key](https://console.groq.com/keys) (free tier) and either Docker or [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env              # set GROQ_API_KEY

# Docker (API + Qdrant)
docker compose up -d --build
make docker-ingest                # fills the index; the API picks it up without a restart

# or locally
make install                      # dependencies, incl. the embedding and OCR extras
make ingest                       # fetch -> parse -> chunk -> index -> vectors (needs no API key)
make api                          # http://localhost:8000
```

## What it does and doesn't do

Ask in plain English, across all documents or limited to one ("Search only in …" in the chat page, or name it: "What does WHO say about …"). The answer is one paragraph. Each sentence comes from one document and cites it, and a sentence names its document where the source changes. Code checks every answer, so no statement blends two documents.

> **Which cooking oils should I use, and is it OK to reuse oil after deep frying?**
>
> According to ICMR-NIN's Dietary Guidelines for Indians, vegetable oil once used for frying should be filtered and may be used for curry preparation, but should not be used for frying again [1]. … Repeated heating of cooking oils generates harmful oxidative (polar) compounds and must be avoided [2]. … According to WHO's healthy diet fact sheet, replace butter, lard and ghee with polyunsaturated oils such as soybean, canola (rapeseed), corn, safflower and sunflower oils [4].
>
> [1] Dietary Guidelines for Indians · ICMR – National Institute of Nutrition · 2024 · Guideline 7 … > Repeated heating of oils · p. 72 · https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf#page=72 …

Nutrient values are answered when a document gives them. "How much protein does milk have?" gets "3.1 g per 100 g raw weight" from ICMR-NIN's food-group table. Foods the documents don't list (paneer, banana) get the not-in-corpus refusal. Per-food nutrient databases are the brief's Milestone 3.

**Refusals** come in two kinds, and both messages are written in code, not by the model:

| Kind | Example | What the assistant says |
|---|---|---|
| Out of scope | "What should I eat to cure my type 2 diabetes?" | "I can't give personal health advice, such as about a health condition, medication, or your own pregnancy or breastfeeding. This assistant only reports what public dietary and food-safety guidance documents say. For advice about your own health, please speak to a registered dietitian or your doctor." Calorie targets and body-weight goals get the same referral. |
| Not in the documents | "What does the guidance say about intermittent fasting?" | "The guidance documents I searched don't cover this question. Searched: Dietary Guidelines for Indians (ICMR – National Institute of Nutrition, 2024); …" (every document searched, or only the filtered one) |
| Unknown document | "What does the NHS say about fibre?" | "NHS isn't in my corpus, so I can't say what it recommends. I can search: …" |

Population guidance stays in scope: "What does WHO say about salt and blood pressure?" is answered. Rules in `scope_rules.yaml` catch out-of-scope questions first, including Hinglish, Hindi and Spanish wordings. A small LLM classifier can only add refusals.

## Corpus

Seven written guidance documents from the brief's list. [corpus/registry.yaml](corpus/registry.yaml) records each one's provenance and the SHA-256 of the downloaded file.

| Document | Publisher | Year | URL | Retrieved |
|---|---|---|---|---|
| Dietary Guidelines for Indians | ICMR – National Institute of Nutrition | 2024 | [nin.res.in … DGI_2024.pdf](https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf) | 2026-10-04 |
| Healthy diet (fact sheet) | World Health Organization | 2026 | [who.int … healthy-diet](https://www.who.int/news-room/fact-sheets/detail/healthy-diet) | 2026-10-04 |
| Cold Food Storage Chart | FoodSafety.gov (U.S. Department of Health and Human Services) | 2023 | [foodsafety.gov … cold-food-storage-charts](https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts) | 2026-10-04 |
| Food Industry Guide to Implement GMP/GHP Requirements: Milk and Milk Products | Food Safety and Standards Authority of India (FSSAI) | 2018 | [fssai.gov.in … Guidance_Document_Milk_14_03_2019.pdf](https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Milk_14_03_2019.pdf) | 2026-10-04 |
| Food Industry Guide to Implement GMP/GHP Requirements: Meat and Meat Products (Poultry) | Food Safety and Standards Authority of India (FSSAI) | 2018 | [fssai.gov.in … Guidance_Document_Poultry_06_01_2020.pdf](https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Poultry_06_01_2020.pdf) | 2026-10-04 |
| Food Industry Guide to Implement GMP/GHP Requirements: Processed Fruits and Vegetables | Food Safety and Standards Authority of India (FSSAI) | 2019 | [fssai.gov.in … FSMS_Guidance_Document_FruitsVegetable_15_03_2019.pdf](https://www.fssai.gov.in/docs/business/guidance/FSMS_Guidance_Document_FruitsVegetable_15_03_2019.pdf) | 2026-10-04 |
| Evaluation of certain food additives: 100th report of the Joint FAO/WHO Expert Committee on Food Additives (WHO TRS 1058) | World Health Organization and Food and Agriculture Organization of the United Nations | 2025 | [who.int … 9789240116030](https://www.who.int/publications/i/item/9789240116030) | 2026-10-04 |

**Excluded:** EFSA's Food Composition data and Health Canada's Canadian Nutrient File. Both are nutrient values per food, not written guidance, and the brief puts that data in Milestone 3. Three FSSAI guides (Spices, Fish, Product Standards) are kept in the registry as reserves.

## Chunking: the choice and what it cost

**Choice: structure-aware chunking.** Each document is parsed into a tree of sections and typed blocks, and chunks follow that structure:
- each numbered recommendation is one chunk;
- tables stay whole up to 800 tokens, and larger ones split between rows with the caption and header repeated in every piece;
- prose and lists are packed under their heading up to 400 tokens.

**Why not fixed-size.** Most answers live in tables (how long food keeps) and numbered recommendations (the ICMR guidelines), and a fixed window cuts both. Re-chunking the same parsed text in 400-token windows with 50 overlap ([eval/results/chunking.md](eval/results/chunking.md)):

| | Fixed-size (400/50) | Structure-aware |
|---|---|---|
| Tables cut across chunks | **69 of 96 (72%)** | none under 800 tokens |
| Pieces with table rows but no header row | **183** | **0** |
| Numbered recommendations cut | **11 of 34 (32%)** | **0** |

This measures whether content stays intact. A retrieval-recall comparison against a fixed-size index was not run.

**What it cost:**
- **Per-document parser settings.** The guides use different heading styles, so each has its own config: pages to skip, heading fonts, table detection.
- **Imperfect tables.** 2 tables are hand-corrected, 7 garbled ones dropped, and 34 have no header row. Two scanned pages go through OCR.
- **Uneven chunk sizes,** from 4 to 774 tokens (median 261). Small ones get a contextual header; a reranker evens out scoring.
- **Hard-to-find tables.** A table under a heading that doesn't name its contents ranked ~60th for a direct question, so table rows are also indexed on their own.
- **More build time** than a stock text splitter.

Result: 903 chunks, and a gold chunk in the top 10 for every answerable golden question (Recall@10 = 1.00).

## Evaluation results

`make eval` runs the golden set ([eval/golden.yaml](eval/golden.yaml): 50 questions in 9 categories, 10 held out for final scoring) through the real pipeline. `make redteam` runs [30 adversarial prompts](eval/redteam.yaml): role-play, "asking for a friend", Hinglish, Hindi, Spanish, disguised medical questions and prompt injection. Results of 2026-10-08:

| Metric | Target | Result |
|---|---|---|
| Retrieval Recall@10 | ≥ 0.90 | **1.00** |
| Out-of-scope refusal recall | 100% | **100%** |
| Not-in-corpus refusal recall | ≥ 95% | **100%** |
| False refusals on answerable questions | ≤ 10% | **3%** (1 of 32) |
| Citation precision (LLM-judged; judge hand-checked 19/20) | ≥ 0.95 | **0.98** |
| Claims blending two documents / without a citation | 0 / 0 | **0 / 0** |
| p95 latency | ≤ 8 s | **8.4 s** ✗ (median 4.3–5.2 s) |

47 of 48 golden questions and 29 of 30 red-team prompts pass. The one failure in both is "I'm cooking for my family. Is it OK to reuse the oil …?", which the evidence check wrongly calls not covered. [eval/results/error_analysis.md](eval/results/error_analysis.md) traces each failure and fix.

These numbers predate answering nutrient questions, which added 4 golden questions. A live check gave the expected results, but `make eval` should be re-run for current numbers.

## Known limitations

- **Frozen documents:** answers use the copies retrieved on 2026-10-04.
- **English only:** in-scope answers are only reliable in English. Out-of-scope rules also cover Hinglish, Hindi and Spanish.
- **Parser-limited tables:** tables are only as good as the parser, and two pages are OCR text.
- **Food-group nutrient values:** values are food-group averages, not per-food. Some answers quote ICMR's infant-recipe boxes, which give no serving size.
- **One known false refusal** (above).
- **Population guidance only:** no personal advice.
- **Free tier:** Groq allows 8,000 tokens a minute and 200,000 a day per model, about 2–3 answers a minute. When the daily quota runs out, `/chat` returns 503 until UTC midnight.
- **Latency:** p95 is just over target on a laptop CPU.

## Development

```bash
make test                         # lint, format, mypy, unit tests (no index or API key needed)
make e2e                          # one golden question per category (needs the index and GROQ_API_KEY)
make eval / make redteam          # full eval -> eval/report.md (needs a day's Groq quota when uncached)
make deploy                       # build and deploy to Google Cloud Run (see deployment-plan.md)
.venv/bin/python scripts/ask.py "How long can I keep leftover pizza in the fridge?"
uv run python -m guidance_rag.ingest parse --dump --doc DOC_ID   # review a document's parse
uv run python -m eval.chunking_comparison                        # the chunking table above
```

- **API:** `POST /chat` takes `{"question": "…", "doc_filter": ["doc-id"]}`. There's also `GET /documents`, `GET /health`, and the chat page at `/`. The contract and error codes are in [ARCHITECTURE.md §10](ARCHITECTURE.md#10-api-contract).
- **Traces:** every `/chat` call appends one line to `logs/traces.jsonl` (evidence, scores, raw model reply, dropped claims, timings). The `trace_id` in each response points to it.
- **Settings** are read from `.env`; [.env.example](.env.example) documents each one.
- **Data:** raw downloads aren't committed. The parsed trees (`corpus/parsed/`), chunks (`corpus/chunks/`) and chunk vectors (`corpus/embeddings.sqlite`) are, and the Docker image is built from them. Table corrections go in `corpus/overrides/{doc_id}/{table_id}.csv`.
- **LLM replies are cached** in `.cache/llm/`, so repeated questions and eval re-runs cost no quota.
- **CI** runs lint, types and tests on every push. A nightly eval workflow needs the `GROQ_API_KEY` repository secret.
- **iCloud:** if the project is in an iCloud-synced folder, keep `.venv` outside it, or imports fail and tools hang:
  ```bash
  uv venv --python 3.12 ~/.venvs/guidance-rag && ln -s ~/.venvs/guidance-rag .venv
  ```
