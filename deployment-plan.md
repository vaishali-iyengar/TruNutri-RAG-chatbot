# Deployment Plan: TruNutri RAG chatbot on Google Cloud Run

This plan deploys the whole project, the backend and the redesigned chat page, as **one public web service on Google Cloud Run**, kept within Cloud Run's free tier. It follows the design in [ARCHITECTURE.md](ARCHITECTURE.md). Steps are written to be followed in order by anyone on the team.

*Written 2026-10-08.*

---

## 1. What gets deployed

One container runs everything. FastAPI serves the chat page and the API from the same address, so the frontend needs no separate hosting, no API URL setting and no CORS setup.

```
Visitor's browser
   │  https://<service>.run.app
   ▼
Cloud Run service "trunutri"  (one container, built from ./Dockerfile)
   ├── GET  /           → chat page (src/guidance_rag/ui/index.html)
   ├── GET  /documents  → list of indexed guidance documents
   ├── GET  /health     → index status
   └── POST /chat       → RAG pipeline
          ├── query embedding + BM25 + reranker   (models baked into the image)
          ├── local Qdrant index                  (baked into the image)
          └── Groq API (answer + scope models)    (GROQ_API_KEY from Secret Manager)
```

## 2. Decisions

| Decision | Choice | Why |
|---|---|---|
| Platform | Google Cloud Run | Runs our existing Dockerfile; free monthly allowance; scales to zero when idle. Railway's free plan gives 0.5 GB RAM per service, too little for the models. |
| Services | One | The page and API share one origin. No separate Qdrant: the local index needs a single process, which one container gives. |
| Index and models | Baked into the image at build time | Cloud Run has no persistent disk. The chunks (`corpus/chunks/`) and their vectors (`corpus/embeddings.sqlite`) are committed, so the build only loads them into the index. No API key is needed to build. |
| Billing mode | Request-based, 0–1 instances | Charged only while answering; one instance caps cost. |
| Memory | 2 GiB, 1 vCPU | Torch plus two models, with headroom. Locally the loaded pipeline peaked at about 0.45 GB; Linux containers usually use more. |
| Secret | `GROQ_API_KEY` in Secret Manager | Keeps the key out of the service config and the image. |
| Region | `us-central1` | A low-cost region where the free tier applies. |

## 3. Prerequisites

- [ ] A Google account, and a Google Cloud project with **billing enabled**. Google requires a card for verification. Within the free tier nothing is charged.
- [ ] A Groq API key (https://console.groq.com/keys).
- [ ] The Google Cloud CLI on the machine you deploy from: `brew install --cask google-cloud-sdk`, then `gcloud init`. To deploy without the CLI, see [Appendix A](#appendix-a-deploying-from-the-console-instead).
- [ ] Push access to `github.com/vaishali-iyengar/TruNutri-RAG-chatbot`.

## 4. Step 1: Prepare the repository

The deployment changes are committed (branch `initial-build`):

| File | What it does for Cloud Run |
|---|---|
| `Dockerfile` | Bakes the reranker, the embedding model and the search index (from the committed vectors) into the image, then switches Hugging Face to offline mode (`HF_HUB_OFFLINE=1`), so a cold start loads everything from the image and never calls the Hub. Listens on `$PORT` (Cloud Run) and falls back to 8000 (docker compose). |
| `corpus/embeddings.sqlite` | The vectors of the current chunks (3.8 MB), written by `python -m guidance_rag.ingest vectors` (the last step of `make ingest`). The build seeds its embedding cache from it, so it doesn't embed the corpus again: that took ~40 minutes on 4 CPUs, which would risk Cloud Build's time limit. A test fails if the file doesn't cover every chunk. |
| `.gcloudignore` | What `--source .` uploads to Cloud Build: everything git ignores stays out (`.env` with the API key, `.venv`, caches, the local index, logs, raw downloads), plus `.git` and the design mockups. |
| `.dockerignore` | Keeps the same files, and the design mockups, out of the image. |
| `Makefile` | `make deploy` runs the Step 3 command (`SERVICE=trunutri`, `REGION=us-central1`; override either on the command line). |
| `src/guidance_rag/ui/index.html`, `api.py` | The TruNutri design and name. |

**Steps:**
- [ ] Run the checks: `make test` (unit tests, lint and type checks).
- [ ] Optional, needs Docker: run the image the way Cloud Run does, on `$PORT` with no network, to check that it starts from what is baked in:
  ```bash
  docker build -t trunutri .
  docker run --rm --network none -e PORT=8080 -e GROQ_API_KEY=x -p 8080:8080 trunutri
  # in another terminal: curl localhost:8080/health   -> {"status":"ok","documents":7}
  ```
- [ ] Push to GitHub and merge into `main` (`git push -u origin initial-build`, then a pull request).

**Done when:** `main` on GitHub has the files above and CI is green.

## 5. Step 2: Set up Google Cloud (once)

Run these from the project folder. Replace `PROJECT_ID` with your project's ID.

```bash
gcloud config set project PROJECT_ID
gcloud config set run/region us-central1

# APIs used by source deploys
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com

# The image build embeds the corpus and downloads models; allow it up to an hour
# (the default build timeout is shorter)
gcloud config set builds/timeout 3600

# Store the Groq key as a secret (paste the key, then press Ctrl-D)
gcloud secrets create groq-api-key --data-file=-

# Let the Cloud Run service account read it
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding groq-api-key \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

- [ ] In the console, open **Billing → Budgets & alerts** and create a budget of **$1** with email alerts. This is the safety net if usage ever leaves the free tier.

**Done when:** `gcloud secrets list` shows `groq-api-key`, and the budget exists.

## 6. Step 3: Deploy

From the project root, on an up-to-date `main`, run `make deploy`, which runs:

```bash
gcloud run deploy trunutri \
    --source . \
    --allow-unauthenticated \
    --memory 2Gi --cpu 1 \
    --min-instances 0 --max-instances 1 \
    --concurrency 10 \
    --timeout 120 \
    --cpu-boost \
    --set-secrets "GROQ_API_KEY=groq-api-key:latest" \
    --set-env-vars "FORWARDED_ALLOW_IPS=*"
```

What the flags do:

- `--source .` builds the Dockerfile on Cloud Build and stores the image in Artifact Registry. On the first run, gcloud offers to create the `cloud-run-source-deploy` repository; answer yes.
- `--allow-unauthenticated` makes the chatbot public.
- `--min-instances 0` scales to zero when idle, which keeps it free. `--max-instances 1` caps cost.
- `--timeout 120` is above the app's own 60-second `/chat` limit (`CHAT_TIMEOUT_S`).
- `--cpu-boost` speeds up model loading on a cold start.
- `FORWARDED_ALLOW_IPS=*` lets uvicorn read the visitor's real IP from Cloud Run's proxy, so the limit of 20 questions per minute applies per visitor. Without it, every visitor shares one limit. This is safe on Cloud Run because only Google's proxy can reach the container.

The first build takes about 10–15 minutes, mostly installing torch and downloading the two models; the index is built from the committed vectors, not by embedding the corpus. Later builds reuse cached layers unless dependencies change.

**Done when:** the command prints `Service URL: https://trunutri-….run.app`.

## 7. Step 4: Verify

Open the service URL and check each item:

- [ ] `https://<service-url>/health` returns `{"status":"ok","documents":7}`. The first call after idle can take 20–40 seconds while the models load.
- [ ] The page shows the TruNutri design: cream background, the "Ask anything about food, nutrition & safety." headline, example cards, and the "Index ready · 7 documents" chip.
- [ ] Click **Single document** (WHO salt): the answer reads as one paragraph with `[n]` badges. **Sources** is collapsed, opens on click, and "View source" links work.
- [ ] Click **Cross-document** (cooking oils): the paragraph names each source ("According to …").
- [ ] Click **Recommendation** (Indian guideline on salt): a cited answer from ICMR-NIN.
- [ ] Type "What should I eat to cure my type 2 diabetes?": the "This question needs a health professional" card appears.
- [ ] Type "What does the guidance say about intermittent fasting?": the "The guidance documents don't cover this" card appears.
- [ ] Type "How much protein does milk have?": answered from ICMR-NIN's food-group table (3.1 g per 100 g).
- [ ] Pick one document in the library and ask a question: the answer cites only that document.
- [ ] Toggle dark mode; check the page on a phone.
- [ ] Run the end-to-end tests against the live service:
  ```bash
  E2E_BASE_URL=https://<service-url> uv run pytest -m e2e
  ```

**Done when:** every box is ticked and the e2e tests pass.

## 8. Updating and rolling back

- **Ship a change:** merge to `main`, pull, and run `make deploy` again. Each deploy creates a new revision. Corpus changes are picked up because the build re-indexes: run `make ingest` first, which also refreshes `corpus/embeddings.sqlite`, and commit both the chunks and the vectors. A chunk missing from the vectors file is embedded during the build, which is slow.
- **Roll back:** in **Cloud Run → trunutri → Revisions**, send 100% of traffic to the previous revision, or run:
  ```bash
  gcloud run services update-traffic trunutri --to-revisions=<REVISION_NAME>=100
  ```
- **Rotate the Groq key:** `gcloud secrets versions add groq-api-key --data-file=-`, then redeploy, or update the service so it picks up `latest`.
- **Logs:** **Cloud Run → trunutri → Logs** shows uvicorn access lines and app warnings. The app's own trace file (`logs/traces.jsonl`) lives inside the container and is lost on restart.

## 9. Cost and the free tier

Cloud Run's monthly free tier for request-based billing is 2 million requests, 180,000 vCPU-seconds and 360,000 GiB-seconds ([pricing](https://cloud.google.com/run/pricing)). At 2 GiB that is about **50 hours of active request time a month**. A demo stays well inside it.

Other costs to watch:

| Item | Expected |
|---|---|
| Artifact Registry image storage | The image is likely 2–3 GB, over the 0.5 GB free storage, so a few cents a month. Delete old images after each deploy, or set a cleanup policy on the `cloud-run-source-deploy` repository. |
| Cloud Build | Within the free daily build minutes for occasional deploys. |
| Secret Manager | Within the free tier (one secret, few accesses). |
| Groq | Free tier, about 1,000 requests a day for `openai/gpt-oss-120b`, shared by all visitors. |

Check the billing page a week after launch to confirm spending is at or near $0.

## 10. Known limitations

- **Cold starts:** after a quiet period, the first visitor waits about 20–40 seconds while the models load. Setting `--min-instances 1` removes this but leaves the free tier.
- **State resets on restart:** the LLM response cache, the Groq usage counter (`.cache/llm/usage.sqlite`) and the trace logs live in the container and reset whenever the instance restarts. Groq still enforces its own quotas server-side.
- **Groq daily quota is shared:** a busy public link can exhaust it, after which `/chat` returns "The answer service is unavailable…" until the quota resets. The per-visitor limit slows this but doesn't prevent it.
- **Fonts load from Google Fonts.** If they are blocked, the page falls back to system serif and sans-serif fonts.
- **Model overrides:** the build bakes the default reranker and embedding models, and the container runs with Hugging Face offline. If the models are changed, the Dockerfile's bake step must use the same ones, or the container can't load them and `/health` reports the error.

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails with a timeout | Build exceeded the Cloud Build limit | `gcloud config set builds/timeout 3600` and redeploy. |
| Build fails with a permission error | The build service account lacks a role | Grant the compute service account `roles/run.builder`, or accept the roles gcloud offers to add. |
| Container exits with "Memory limit exceeded" | Out of memory | Redeploy with `--memory 4Gi`. This halves the free hours. |
| `/health` returns 503 with a Qdrant "already accessed" error | Two processes opened the local index | Keep the default single uvicorn process; don't add `--workers`. |
| `/chat` returns 503 "answer service is unavailable" | Groq quota or outage, or a missing or invalid key | Check the secret binding (Step 2) and Groq's console usage. |
| Every visitor gets "Too many questions" | `FORWARDED_ALLOW_IPS` not set | Add `--set-env-vars "FORWARDED_ALLOW_IPS=*"` and redeploy. |
| Page loads, but `/documents` or `/chat` returns 404 | Wrong service, or an old revision is serving traffic | Check **Revisions** and send traffic to the latest one. |
| `/health` returns 503 mentioning "offline mode" or huggingface.co | A model the app loads isn't baked into the image | Bake the same models the code uses (Dockerfile bake step), and redeploy. |

---

## Appendix A: Deploying from the Console instead

For a one-time setup without the CLI, using continuous deployment from GitHub:

1. Do Steps 1 and 2 (create the secret and budget in the console: **Security → Secret Manager**, **Billing → Budgets**).
2. **Cloud Run → Deploy container → Continuously deploy from a repository.** Connect GitHub, choose `TruNutri-RAG-chatbot`, branch `main`, build type **Dockerfile**.
3. Settings: **Allow public access**; **Request-based** billing; min 0 and max 1 instances; **2 GiB** memory, **1** CPU; **Startup CPU boost** on; request timeout **120 s**; maximum concurrent requests **10**.
4. **Variables & Secrets:** reference secret `groq-api-key` as env var `GROQ_API_KEY`, and add env var `FORWARDED_ALLOW_IPS` = `*`.
5. Create. If the first build times out, raise the build trigger's timeout in **Cloud Build → Triggers** and re-run it.

Every push to `main` then rebuilds and redeploys automatically. Verify with Step 4.
