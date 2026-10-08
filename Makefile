# Common tasks (implementation-plan.md, 8.5). `make help` lists them.
#
# Targets run locally with uv. For the Docker stack, use the docker-* targets, or pass
# RUN, e.g. `make ingest RUN="docker compose exec api"`.

RUN ?= uv run
INGEST = $(RUN) python -m guidance_rag.ingest
PORT ?= 8000
# Google Cloud Run (deployment-plan.md). Needs gcloud, a project set with
# `gcloud config set project …`, and the groq-api-key secret.
SERVICE ?= trunutri
REGION ?= us-central1

.PHONY: help install ingest api ui test e2e eval redteam lint docker-up docker-ingest docker-e2e deploy

help:
	@echo "install        uv sync with the embed and ocr extras"
	@echo "ingest         fetch -> parse -> chunk -> index -> vectors (all included documents)"
	@echo "api            serve the API and chat page on http://localhost:$(PORT)"
	@echo "ui             open the chat page in a browser (the API must be running)"
	@echo "test           unit tests, lint and type checks (no index or API key needed)"
	@echo "e2e            end-to-end tests (need the index and GROQ_API_KEY)"
	@echo "eval           full eval (all questions, judged) -> eval/report.md"
	@echo "redteam        the red-team prompts through the full pipeline"
	@echo "docker-up      build and start the API and Qdrant"
	@echo "docker-ingest  run the ingest inside the api container"
	@echo "docker-e2e     end-to-end tests against the running Docker stack"
	@echo "deploy         build and deploy to Google Cloud Run (SERVICE=$(SERVICE), REGION=$(REGION))"

install:
	uv sync --extra embed --extra ocr

ingest:
	$(INGEST) fetch
	$(INGEST) parse --save
	$(INGEST) chunk
	$(INGEST) index
	$(INGEST) vectors

api:
	$(RUN) uvicorn guidance_rag.api:app --host 0.0.0.0 --port $(PORT)

ui:
	$(RUN) python -m webbrowser http://localhost:$(PORT)

test: lint
	$(RUN) pytest -m "not e2e"

e2e:
	$(RUN) pytest -m e2e

eval:
	$(RUN) python -m eval.run_eval --split all --judge --out eval/report.md

redteam:
	$(RUN) python -m eval.run_eval --set eval/redteam.yaml --split all --out eval/results/redteam.md

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

docker-up:
	docker compose up -d --build

docker-ingest:
	$(MAKE) ingest RUN="docker compose exec api"

docker-e2e:
	E2E_BASE_URL=http://localhost:$(PORT) $(RUN) pytest -m e2e

deploy:
	gcloud run deploy $(SERVICE) --source . --region $(REGION) \
		--allow-unauthenticated \
		--memory 2Gi --cpu 1 \
		--min-instances 0 --max-instances 1 \
		--concurrency 10 --timeout 120 --cpu-boost \
		--set-secrets "GROQ_API_KEY=groq-api-key:latest" \
		--set-env-vars "FORWARDED_ALLOW_IPS=*"
