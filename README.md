# TruNutri RAG Chatbot

A chatbot that answers questions about food, nutrition and food safety **only** from seven official public guidance documents (ICMR-NIN, WHO, FSSAI, FoodSafety.gov, JECFA). Every statement carries a citation: document, publisher, year, section, page and a link. When the documents don't cover a question, it says so and names what it searched. It refuses medical advice, personal calorie targets and body-weight goals in code, before any search or language model runs.

- Brief: [problem-statement.md](problem-statement.md)
- Design: [ARCHITECTURE.md](ARCHITECTURE.md)
- Build log, decisions and measurements: [implementation-plan.md](implementation-plan.md)
- Deployment to Google Cloud Run: [deployment-plan.md](deployment-plan.md)

## Quick start

You need a [Groq API key](https://console.groq.com/keys) (free tier) and either Docker or [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env              # then set GROQ_API_KEY

# Option A: Docker (API + Qdrant server)
docker compose up -d --build      # first build takes several minutes
make docker-ingest                # fills the Qdrant server; the API picks it up without a restart
open http://localhost:8000

# Option B: local
make install                      # uv sync with the embed and ocr extras
make ingest                       # fetch -> parse -> chunk -> index (several minutes; needs no API key)
make api                          # http://localhost:8000
```

`make help` lists every target. Setup details are in [Development](#development).

## What it does and doesn't do

Ask in plain English, optionally limited to one document ("Search only in …" in the chat page, or name it: "What does WHO say about …").

**Answers.** The answer is one paragraph. Each sentence is one statement from one document, with its own citation. Where the answer moves to another document, the sentence names it. Statements from different documents are never blended into one claim; code checks this on every answer.

> **Which cooking oils should I use, and is it OK to reuse oil after deep frying?**
>
> According to ICMR-NIN's Dietary Guidelines for Indians, vegetable oil once used for frying should be filtered and may be used for curry preparation, but should not be used for frying again [1]. Used oil should be consumed within a day or two and should not be stored for a long time [1]. Repeated heating of cooking oils generates harmful oxidative (polar) compounds and must be avoided [2]. Repeated use of oils used for frying should be avoided, and already used oils should not be mixed with fresh oils and reused [3]. According to WHO's healthy diet fact sheet, replace butter, lard and ghee with polyunsaturated oils such as soybean, canola (rapeseed), corn, safflower and sunflower oils [4].
>
> [1] Dietary Guidelines for Indians · ICMR – National Institute of Nutrition · 2024 · GUIDELINE 7 Use oils/fats in moderation … > Repeated heating of oils · p. 72 · https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf#page=72
> [2]–[4] … (one line per citation: title, publisher, year, section, page, link)

Nutrient values are answered when a document gives them. ICMR-NIN's Table 1.3 lists averages per 100 g for 17 food groups, so "How much protein does milk have?" gets "3.1 g per 100 g raw weight" with a citation. Values for single foods the documents don't list (paneer, banana) get the not-in-corpus refusal below. Per-food nutrient databases are the brief's Milestone 3, not part of this assistant.

**Refusals.** There are two kinds, and both messages are written in code, not by the model.

| Kind | Example question | What the assistant says |
|---|---|---|
| **Out of scope: medical** | "What should I eat to cure my type 2 diabetes?" | "I can't give personal health advice, such as about a health condition, medication, or your own pregnancy or breastfeeding. This assistant only reports what public dietary and food-safety guidance documents say. For advice about your own health, please speak to a registered dietitian or your doctor." |
| **Out of scope: calorie target** | "How many calories should I eat to lose weight?" | "I can't set personal calorie targets or calorie-based meal plans. …" (same referral) |
| **Out of scope: body weight** | "How much should a 30-year-old woman weigh?" | "I can't advise on personal body-weight goals, BMI or weight-loss targets. …" (same referral) |
| **Not in the documents** | "What does the guidance say about intermittent fasting?" | "The guidance documents I searched don't cover this question. Searched: Dietary Guidelines for Indians (ICMR – National Institute of Nutrition, 2024); Healthy diet (fact sheet) (World Health Organization, 2026); …" (every document searched, or only the one you filtered to) |
| **Unknown document** | "What does the NHS say about fibre?" | "NHS isn't in my corpus, so I can't say what it recommends. I can search: Dietary Guidelines for Indians (…); …" |

Population guidance stays in scope even when it touches health: "What does WHO say about salt and blood pressure?" is answered. Out-of-scope questions are caught by rules first (`src/guidance_rag/query/scope_rules.yaml`, which also cover Hinglish, Hindi and Spanish wordings). A small LLM classifier can only add refusals, and a final check removes any calorie or weight target addressed to "you" from a drafted answer.

## Corpus

Seven documents, chosen from the brief's list for being written guidance. The registry, [corpus/registry.yaml](corpus/registry.yaml), records each document's provenance and a SHA-256 of the downloaded file.

| Document | Publisher | Year | URL | Retrieved |
|---|---|---|---|---|
| Dietary Guidelines for Indians | ICMR – National Institute of Nutrition | 2024 | [nin.res.in … DGI_2024.pdf](https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf) | 2026-10-04 |
| Healthy diet (fact sheet) | World Health Organization | 2026 | [who.int … healthy-diet](https://www.who.int/news-room/fact-sheets/detail/healthy-diet) | 2026-10-04 |
| Cold Food Storage Chart | FoodSafety.gov (U.S. Department of Health and Human Services) | 2023 | [foodsafety.gov … cold-food-storage-charts](https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts) | 2026-10-04 |
| Food Industry Guide to Implement GMP/GHP Requirements: Milk and Milk Products | Food Safety and Standards Authority of India (FSSAI) | 2018 | [fssai.gov.in … Guidance_Document_Milk_14_03_2019.pdf](https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Milk_14_03_2019.pdf) | 2026-10-04 |
| Food Industry Guide to Implement GMP/GHP Requirements: Meat and Meat Products (Poultry) | Food Safety and Standards Authority of India (FSSAI) | 2018 | [fssai.gov.in … Guidance_Document_Poultry_06_01_2020.pdf](https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Poultry_06_01_2020.pdf) | 2026-10-04 |
| Food Industry Guide to Implement GMP/GHP Requirements: Processed Fruits and Vegetables | Food Safety and Standards Authority of India (FSSAI) | 2019 | [fssai.gov.in … FSMS_Guidance_Document_FruitsVegetable_15_03_2019.pdf](https://www.fssai.gov.in/docs/business/guidance/FSMS_Guidance_Document_FruitsVegetable_15_03_2019.pdf) | 2026-10-04 |
| Evaluation of certain food additives: 100th report of the Joint FAO/WHO Expert Committee on Food Additives (WHO TRS 1058) | World Health Organization and Food and Agriculture Organization of the United Nations | 2025 | [who.int … 9789240116030](https://www.who.int/publications/i/item/9789240116030) | 2026-10-04 |

The FoodSafety.gov page blocks scripted downloads, so it was fetched from an archived copy; citations still link to the live page.

**Excluded:**
- **EFSA Food Composition data** is an interactive dashboard of nutrient values, not written guidance.
- **Health Canada's Canadian Nutrient File** is tables of nutrient values per food.

The brief puts nutrient numbers for individual foods in the Milestone 3 database. Three FSSAI documents (Spices, Fish, Product Standards) are kept in the registry as reserves; swapping one in is a one-line change.

## How it works

```
question ─► scope rules ─► (LLM classifier ∥ query analysis → hybrid retrieval → rerank)
         ─► sufficiency gate ─► grounded generation (strict JSON) ─► citation validator
         ─► output check ─► one-paragraph answer with citations built from chunk metadata
```

- **Retrieval:** dense (`gte-modernbert-base`) + BM25, fused with RRF, globally and inside each document, plus table rows, then reranked by a cross-encoder (`ms-marco-MiniLM-L-12-v2`).
- **Generation:** on Groq (`openai/gpt-oss-120b`). The model returns claims with chunk IDs only. Titles, publishers, years, pages and links are filled in by code, so the model can't invent a citation.
- **Validator:** drops any claim that cites nothing, cites a chunk that wasn't retrieved, cites another document's chunk, or states a number that isn't in the cited text.

Details and the reasons behind each choice: [ARCHITECTURE.md](ARCHITECTURE.md).

## Chunking: the choice and what it cost

**Choice: structure-aware chunking.** Each PDF and HTML page is first parsed into a document tree of sections and typed blocks (paragraph, list, table, numbered recommendation). The chunker then walks that tree:
- **Recommendations:** each numbered recommendation is one chunk, whatever its length.
- **Tables:** a table stays whole up to 800 tokens. Larger tables are split between rows into groups of up to 600 tokens, with the caption and header row repeated in every piece.
- **Prose and lists:** packed under their own heading up to 400 tokens, split only at paragraph or list-item boundaries.
- **Small sections:** sibling sections under 120 tokens are merged.
- **Search header:** every chunk carries a short contextual header (`[ICMR-NIN DGI 2024] [Section: Guideline 7 > Repeated heating of oils]`) for search.

**Why not fixed-size chunking.** The answers people ask for live in tables (how long food keeps in the fridge) and numbered recommendations (the ICMR guidelines). A fixed window cuts both, separating values from their column names and rationales from their recommendation. To check, the same parsed text was re-chunked the way a text splitter would cut it, in 400-token windows with 50 tokens of overlap (`python -m eval.chunking_comparison`, [eval/results/chunking.md](eval/results/chunking.md)):

| | Fixed-size (400/50) | Structure-aware |
|---|---|---|
| Tables cut across chunks | **69 of 96 (72%)** | none under 800 tokens; larger ones split between rows |
| Pieces holding table rows without their header row | **183** | **0** (header repeated in every piece) |
| Numbered recommendations cut | **11 of 34 (32%)** | **0** |
| Chunks | 661 | 903 |

This measures whether content stays intact, not retrieval quality. A recall comparison against a fixed-size index was not run.

**What it cost:**
- **A parser tuned per document.** The ICMR guidelines and the FSSAI guides use different heading styles, so each document has its own parser settings in the registry (pages to skip, heading font sizes and patterns, table detection). Tuning and reviewing them was most of Phases 2 and 3.
- **Table fixes by hand.** PyMuPDF's table detection got 2 FSSAI Milk tables wrong; they are hand-corrected as CSV overrides in `corpus/overrides/`. 7 garbled tables are dropped, 34 tables have no detectable header row, and JECFA's tables (no ruling lines) are kept as text. Two FSSAI Milk pages are scans and go through OCR (RapidOCR); their chunks are marked, and OCR text can contain errors.
- **Uneven chunk sizes.** Sizes range from 4 to 774 tokens (median 261; 10th percentile 69, 90th percentile 497). Small chunks carry little context, so each gets the contextual header; big ones blur embeddings, so a reranker scores the candidates.
- **Repeated headers.** Repeating a table's caption and header in every piece adds tokens and makes the pieces of one table score alike. Retrieval therefore adds the other pieces of a table it finds, and keeps at most 3 per table in the evidence.
- **Some tables still hard to find.** A table can sit under a heading that doesn't say what it lists. ICMR's food-group nutrient table ranked about 60th for "How much protein does milk have?", so table rows are also indexed on their own, each with its caption and column names.
- **More engineering than a text splitter.** It took longer to build than a `RecursiveCharacterTextSplitter`, but cut tables are the main way this corpus would fail.

Result: **903 chunks** (493 prose, 178 list, 198 table, 34 recommendation). Retrieval found a gold chunk in the top 10 for every answerable golden question (Recall@10 = 1.00).

## Evaluation results

The golden set, [eval/golden.yaml](eval/golden.yaml), has 50 questions across 9 categories:
- single-document, table lookup, numbered recommendation, document-filtered and cross-document;
- not in the documents, unknown document;
- out of scope, and near misses that must not be refused.

10 of them (about 20% of each category) are held out for final scoring. A separate set of 30 red-team prompts, [eval/redteam.yaml](eval/redteam.yaml), covers role-play, "asking for a friend", Hinglish, Hindi, Spanish, medical questions disguised as food safety, and prompt injection. `make eval` runs the golden set through the real pipeline and writes [eval/report.md](eval/report.md).

Results of 2026-10-08:

| Metric | Target | Result |
|---|---|---|
| Retrieval Recall@10 | ≥ 0.90 | **1.00** |
| Out-of-scope refusal recall | 100% | **100%** (golden 11/11; red team 23/23 by the rules alone) |
| Not-in-corpus refusal recall | ≥ 95% | **100%** |
| False refusals on answerable questions | ≤ 10% | **3%** (1 of 32) |
| Citation precision (LLM-judged) | ≥ 0.95 | **0.98** (104 of 106 claims; the judge agreed with a hand check on 19 of 20) |
| Claims blending two documents | 0 | **0** |
| Claims without a citation | 0 | **0** |
| p95 latency | ≤ 8 s | **8.4 s** ✗ (median 4.3–5.2 s; 6 questions answered live, quota waits excluded) |

Overall, 47 of 48 golden questions and 29 of 30 red-team prompts pass. The one failure in both is the same question, "I'm cooking for my family. Is it OK to reuse the oil …?". The small model that checks whether the passages answer the question says no, although they do. Making it reason harder fixed that question, but also made it answer a question the documents don't cover, so it was left as is. [eval/results/error_analysis.md](eval/results/error_analysis.md) sorts every failure by the stage where it went wrong and lists the fixes.

These numbers were measured before nutrient questions became answerable. That change added four golden questions (milk protein, pulses energy, paneer and banana), replaced the two former nutrient-lookup refusals, and changed the evidence for 8 others. A live check gave the expected results (milk 3.1 g protein and pulses 323 kcal per 100 g; paneer and banana not in the documents), but the full eval has not been re-run since. Run `make eval` once a day's Groq quota is free.

Latency is just over target on an 8 GB laptop. The slowest step is reranking two-part questions on the CPU, and it varies with machine load.

## Known limitations

- **Frozen documents.** Answers come from the copies retrieved on 2026-10-04. `ingest fetch --refresh` reports when a source has changed, but the index isn't updated automatically.
- **English only.** Questions in other languages are refused if out of scope (the rules cover Hinglish, Hindi and Spanish wordings), but in-scope questions are only reliable in English: the documents, embeddings and reranker are English.
- **Tables are only as good as the parser.** 7 garbled tables are dropped, 2 are hand-corrected, JECFA's tables are kept as text, and 34 tables have no header row. Two FSSAI Milk pages are OCR text and can contain recognition errors.
- **Nutrient values are food-group averages.** ICMR's Table 1.3 gives values for groups like "milk" or "pulses", not for specific foods. Some answers also quote nutrition boxes from ICMR's infant-feeding recipes, which give no serving size ("Egg, boiled contains 3.61 g protein").
- **One known false refusal.** "I'm cooking for my family. Is it OK to reuse the oil …?" gets "not in the documents" (see above).
- **Population guidance, not advice.** The assistant reports what the documents say about people in general. It doesn't tailor answers to a person, and it refuses questions about someone's own health, calories or weight.
- **Free-tier limits.** Groq's free tier allows 8,000 tokens a minute and 200,000 a day per model, so the assistant answers 2–3 questions a minute. When the daily quota runs out, `/chat` returns 503 until it resets (UTC midnight).
- **Latency.** The p95 latency target is narrowly missed on a laptop CPU (see above).

## Development

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 automatically.

```bash
uv sync --extra ocr --extra embed   # dependencies; OCR and the embedding model are optional extras
cp .env.example .env          # then fill in GROQ_API_KEY (LLM calls run on Groq)
uv run pre-commit install     # optional: run checks before each commit

make test                     # lint, format check, mypy and unit tests (no index or API key needed)
make e2e                      # end-to-end: one golden question per category (needs the index and GROQ_API_KEY)
uv run pytest -m "not corpus" # skip the slower tests that parse the real corpus
```

Settings are read from `.env`; [.env.example](.env.example) documents each one. The main ones are `GROQ_API_KEY`, `QDRANT_URL` (use a Qdrant server instead of the local index), `SCOPE_CLASSIFIER` (the LLM classifier, on by default), `CHAT_TIMEOUT_S` (60) and `CHAT_RATE_PER_MINUTE` (20).

### Keep the virtual environment out of iCloud

If the project lives in an iCloud-synced folder (Desktop or Documents with iCloud Drive), don't keep `.venv` inside it. iCloud marks the files as hidden, which makes Python 3.12 skip the editable-install `.pth` file (`ModuleNotFoundError: No module named 'guidance_rag'`), and "Optimize Mac Storage" can make reads block, so tools hang. Put the environment outside iCloud and link to it:

```bash
rm -rf .venv
uv venv --python 3.12 ~/.venvs/guidance-rag
ln -s ~/.venvs/guidance-rag .venv
uv sync --extra ocr --extra embed
```

### Ingestion

`make ingest` runs the steps below, from fetching to writing the vectors file. Each can also run on its own, for all documents or one (`--doc DOC_ID`).

```bash
uv run python -m guidance_rag.ingest fetch             # download included documents (skips ones already present)
uv run python -m guidance_rag.ingest fetch --refresh   # re-download to detect changes at the source
uv run python -m guidance_rag.ingest check             # pages, text layer and title check per file
uv run python -m guidance_rag.ingest parse --save      # document trees -> corpus/parsed/{doc_id}.json
uv run python -m guidance_rag.ingest chunk             # chunks -> corpus/chunks/{doc_id}.jsonl, QC -> corpus/qc/
uv run python -m guidance_rag.ingest index             # embed changed chunks and update the index
uv run python -m guidance_rag.ingest vectors           # chunk vectors -> corpus/embeddings.sqlite (for the Docker build)
```

- **Parsing.** Each raw file becomes a document tree: nested sections holding typed blocks with page numbers. Cover pages, contents, reference lists, blank record templates and personalised meal plans are left out. Per-document settings live in the `parser` entry of each document in the registry, with a `notes` line explaining them. `parse --dump --doc DOC_ID` prints a document's outline, block counts and tables; `parse --full` adds every block's text, for review. A saved tree carries a fingerprint of the raw file, parser config, table overrides and parser code, and is re-parsed when any of them changes.
- **OCR.** Scanned pages (FSSAI Milk pp. 74–75) are read with RapidOCR (`uv sync --extra ocr`). Without it, those pages are skipped with a warning.
- **Table corrections.** When a table is parsed wrongly, save the right version as `corpus/overrides/{doc_id}/{table_id}.csv` (first row = header). `parse --dump` shows the `table_id`.
- **Chunk files.** Each line of `corpus/chunks/{doc_id}.jsonl` is one chunk: document, publisher, year, section path, pages, deep link, the body (`text`) and the search text (`embed_text`, the body behind a short document and section header). The QC report per document lists sizes, split tables and any table that looks broken. The raw downloads are not committed; the parsed trees and chunks are, so a parser or chunker change shows up as a diff.
- **Index.** Chunks are embedded with `Alibaba-NLP/gte-modernbert-base` (the first run downloads ~0.6 GB) and stored in a local Qdrant index in `.index/`, with vectors cached in `.cache/embeddings/`, so re-indexing only embeds changed chunks. `index --force` rebuilds the collection. The BM25 indexes over chunks and table rows are built in memory at start-up. `vectors` writes the current chunks' vectors to `corpus/embeddings.sqlite` (committed), so the Docker image is built from them instead of re-embedding the corpus; commit it together with the chunks.

### Running

```bash
make api                          # API and chat page on http://localhost:8000
.venv/bin/python scripts/ask.py "How long can I keep leftover pizza in the fridge?"   # one question from the terminal
.venv/bin/python scripts/ask.py --doc who-healthy-diet "What about trans fats?"
```

The API: `POST /chat` (`{"question": "…", "doc_filter": ["doc-id"]}`), `GET /documents`, `GET /health`, and the chat page at `/`. The response contract and error codes are in [ARCHITECTURE.md §10](ARCHITECTURE.md#10-api-contract). Every `/chat` call appends one line to `logs/traces.jsonl`, including the evidence and scores, the model's raw reply, dropped claims, per-stage timings and the final status. The `trace_id` in each response points to that line.

**Docker:** `docker compose up -d --build` runs the API with a Qdrant server; `make docker-ingest` fills that server (the API loads it without a restart). The image also bakes in both models and an index built from the committed chunks, for single-container hosts without a disk such as Cloud Run ([deployment-plan.md](deployment-plan.md)); Compose ignores that index. After changing the corpus, run `make docker-ingest` again, then `docker compose restart api`.

**Google Cloud Run:** `make deploy` builds the image on Cloud Build and deploys it as one public service (models and index baked in, the Groq key from Secret Manager). One-time setup, costs and checks: [deployment-plan.md](deployment-plan.md).

**LLM replies are cached** in `.cache/llm/`, keyed on the whole request, so repeated questions and eval re-runs cost no Groq quota. A client-side rate limiter keeps requests within the free tier; when the daily quota runs out, `/chat` returns 503 instead of an answer.

### Evaluation

```bash
make eval                         # golden set, judged, -> eval/report.md (needs a day's Groq quota when uncached)
make redteam                      # red-team prompts -> eval/results/redteam.md
uv run python -m eval.run_eval --split dev                          # tuning split only (holdout untouched)
uv run python -m eval.run_eval --no-cache --id sd-01 --id cd-01      # live latency
uv run python -m eval.run_retrieval_eval                            # retrieval only (no LLM)
uv run python -m eval.chunking_comparison                           # structure-aware vs. fixed-size chunking
```

CI (`.github/workflows/ci.yml`) runs lint, types and unit tests on every push. A nightly workflow (`eval.yml`, also startable by hand) builds the index, runs the judged eval and fails if a target is missed. It needs the `GROQ_API_KEY` repository secret.
