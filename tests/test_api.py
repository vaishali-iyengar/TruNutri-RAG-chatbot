"""The API with a fake pipeline (implementation-plan.md, 8.1-8.3).

The pipeline is the real one over a fake retriever and a fake LLM, so /chat returns real
§10 answers and the trace log gets real content.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from guidance_rag.api import MAX_QUESTION_CHARS, ChatPipeline, create_app
from guidance_rag.generator import Generator
from guidance_rag.pipeline import Pipeline, RagAnswerer
from guidance_rag.query.analyzer import QueryAnalyzer
from guidance_rag.registry import load_registry
from guidance_rag.tracing import TraceLog
from tests.fakes import DGI_OILS, WHO_FATS, FakeLLM, FakeRetriever, evidence
from tests.test_pipeline import OIL_REPLY

REGISTRY = load_registry()
DOC_IDS = [d.doc_id for d in REGISTRY.included]
OIL_QUESTION = "Which cooking oils should I use, and is it OK to reuse oil after deep frying?"


def fake_pipeline(*replies: str) -> tuple[Pipeline, FakeRetriever, FakeLLM]:
    retriever = FakeRetriever(evidence(DGI_OILS, WHO_FATS))
    llm = FakeLLM(*replies)
    answerer = RagAnswerer(QueryAnalyzer(REGISTRY), retriever, Generator(llm), REGISTRY)  # type: ignore[arg-type]
    return Pipeline(answerer), retriever, llm


def client_for(factory: Callable[[], ChatPipeline], log_path: Path) -> TestClient:
    app = create_app(factory, REGISTRY, TraceLog(log_path))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "traces.jsonl"


@pytest.fixture
def client(log_path: Path) -> Iterator[TestClient]:
    pipeline, _, _ = fake_pipeline(OIL_REPLY)
    with client_for(lambda: pipeline, log_path) as c:
        yield c


def traces(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- 8.1 Endpoints -----------------------------------------------------------------------


def test_chat_returns_the_api_answer(client: TestClient) -> None:
    res = client.post("/chat", json={"question": OIL_QUESTION})

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "answered"
    assert body["refusal"] is None
    assert [s["doc_id"] for s in body["sections"]] == ["icmr-nin-dgi-2024", "who-healthy-diet"]
    assert body["sections"][0]["claims"][0]["citations"] == [1]
    assert body["sections"][0]["publisher"] and body["sections"][0]["year"]
    assert [c["n"] for c in body["citations"]] == [1, 2]
    assert body["citations"][0]["url"].startswith("http")
    assert len(body["trace_id"]) == 32


def test_chat_passes_the_doc_filter(log_path: Path) -> None:
    pipeline, retriever, _ = fake_pipeline(OIL_REPLY)
    with client_for(lambda: pipeline, log_path) as c:
        res = c.post("/chat", json={"question": OIL_QUESTION, "doc_filter": ["who-healthy-diet"]})

    assert res.status_code == 200
    _, doc_ids, _ = retriever.calls[0]
    assert doc_ids == ["who-healthy-diet"]


def test_a_refusal_is_returned_with_its_message(client: TestClient) -> None:
    res = client.post("/chat", json={"question": "What should I eat to cure my diabetes?"})

    body = res.json()
    assert res.status_code == 200
    assert body["status"] == "out_of_scope"
    assert body["refusal"]["category"] == "medical"
    assert "dietitian" in body["refusal"]["message"]
    assert body["sections"] == [] and body["citations"] == []


def test_documents_lists_the_included_registry_entries(client: TestClient) -> None:
    res = client.get("/documents")

    assert res.status_code == 200
    docs = res.json()
    assert [d["doc_id"] for d in docs] == DOC_IDS
    for d in docs:
        assert d["title"] and d["publisher"] and d["year"] and d["source_url"].startswith("http")
        assert d["retrieval_date"]


def test_health_is_ok_once_the_pipeline_is_loaded(client: TestClient) -> None:
    res = client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "documents": len(DOC_IDS)}


def test_the_pipeline_is_loaded_once_at_startup(log_path: Path) -> None:
    loads: list[int] = []

    def factory() -> ChatPipeline:
        loads.append(1)
        return fake_pipeline(OIL_REPLY, OIL_REPLY)[0]

    with client_for(factory, log_path) as c:
        assert loads == [1]  # before any request
        c.post("/chat", json={"question": OIL_QUESTION})
        c.post("/chat", json={"question": OIL_QUESTION})
    assert loads == [1]


def test_without_an_index_health_and_chat_say_so_until_it_loads(log_path: Path) -> None:
    ready = False

    def factory() -> ChatPipeline:
        if not ready:
            raise RuntimeError("no index: run `python -m guidance_rag.ingest index` first")
        return fake_pipeline(OIL_REPLY)[0]

    with client_for(factory, log_path) as c:
        health = c.get("/health")
        assert health.status_code == 503
        assert "no index" in health.json()["error"]
        chat = c.post("/chat", json={"question": OIL_QUESTION})
        assert chat.status_code == 503
        assert "no index" in chat.json()["detail"]

        ready = True  # e.g. `make ingest` finished
        assert c.get("/health").status_code == 200  # health alone retries the load
        assert c.post("/chat", json={"question": OIL_QUESTION}).status_code == 200


def test_a_pipeline_error_is_a_500_with_the_trace_id(log_path: Path) -> None:
    class Broken:
        def run(self, question: str, doc_filter: Any = None, trace: Any = None) -> Any:
            raise ValueError("boom")

        def close(self) -> None:
            pass

    with client_for(lambda: Broken(), log_path) as c:
        res = c.post("/chat", json={"question": OIL_QUESTION})

    assert res.status_code == 500
    trace_id = res.json()["trace_id"]
    [line] = traces(log_path)
    assert line["trace_id"] == trace_id
    assert line["error"] == "ValueError: boom"


def test_the_chat_page_is_served(client: TestClient) -> None:
    res = client.get("/")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "/documents" in res.text and "/chat" in res.text


# --- 8.2 Request validation --------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"question": ""}, "question is empty"),
        ({"question": "   \n "}, "question is empty"),
        ({"question": "x" * (MAX_QUESTION_CHARS + 1)}, "at most 1000 characters"),
        ({}, "Field required"),
        ({"question": "Is salt bad?", "doc_ids": ["who-healthy-diet"]}, "Extra inputs"),
    ],
)
def test_bad_questions_get_a_422(
    client: TestClient, log_path: Path, payload: dict[str, Any], message: str
) -> None:
    res = client.post("/chat", json=payload)

    assert res.status_code == 422
    assert message in json.dumps(res.json()["detail"])
    assert not log_path.exists()  # rejected before the pipeline: nothing to trace


def test_an_unknown_doc_id_gets_a_422_listing_the_valid_ones(client: TestClient) -> None:
    res = client.post("/chat", json={"question": "Is salt bad?", "doc_filter": ["nhs-eatwell"]})

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "nhs-eatwell" in detail
    for doc_id in DOC_IDS:
        assert doc_id in detail


def test_an_empty_doc_filter_searches_everything(log_path: Path) -> None:
    pipeline, retriever, _ = fake_pipeline(OIL_REPLY)
    with client_for(lambda: pipeline, log_path) as c:
        res = c.post("/chat", json={"question": OIL_QUESTION, "doc_filter": []})

    assert res.status_code == 200
    _, doc_ids, _ = retriever.calls[0]
    assert doc_ids is None


# --- 8.3 Tracing -------------------------------------------------------------------------


def test_each_chat_call_adds_one_complete_trace_line(client: TestClient, log_path: Path) -> None:
    res = client.post("/chat", json={"question": OIL_QUESTION})

    [trace] = traces(log_path)
    assert trace["trace_id"] == res.json()["trace_id"]
    assert trace["question"] == OIL_QUESTION
    assert trace["doc_filter"] is None
    assert trace["guard"] == {"allowed": True, "category": None, "rule": None}
    assert trace["analysis"]["status"] == "ok"
    retrieval = trace["retrieval"]
    assert [c for c, _ in retrieval["evidence"]] == [DGI_OILS, WHO_FATS]
    assert all(isinstance(s, float) for _, s in retrieval["evidence"])
    assert retrieval["docs_searched"]
    assert json.loads(trace["llm_raw"]) == json.loads(OIL_REPLY)
    assert trace["generation"] == "answered"
    assert trace["dropped"] == []
    assert trace["status"] == "answered"
    assert trace["citations"] == [DGI_OILS, WHO_FATS]
    assert trace["latency_ms"] > 0
    assert trace["error"] is None

    client.post("/chat", json={"question": OIL_QUESTION})
    assert len(traces(log_path)) == 2


def test_an_out_of_scope_trace_names_the_rule_and_has_no_retrieval(
    client: TestClient, log_path: Path
) -> None:
    client.post("/chat", json={"question": "What should I eat to cure my diabetes?"})

    [trace] = traces(log_path)
    assert trace["guard"]["allowed"] is False
    assert trace["guard"]["category"] == "medical"
    assert trace["guard"]["rule"]
    assert trace["retrieval"] is None and trace["llm_raw"] is None
    assert trace["status"] == "out_of_scope"
    assert trace["refusal"] == "medical"


def test_dropped_claims_are_traced(log_path: Path) -> None:
    bad = json.dumps(
        {
            "status": "answered",
            "claims": [
                {"doc_id": "who-healthy-diet", "text": "Reuse oil.", "chunk_ids": [DGI_OILS]},
                {
                    "doc_id": "icmr-nin-dgi-2024",
                    "text": "Repeated heating of vegetable oils results in oxidation of PUFA.",
                    "chunk_ids": [DGI_OILS],
                },
            ],
            "not_covered": None,
        }
    )
    pipeline, _, _ = fake_pipeline(bad)
    with client_for(lambda: pipeline, log_path) as c:
        assert c.post("/chat", json={"question": OIL_QUESTION}).json()["status"] == "answered"

    [trace] = traces(log_path)
    [dropped] = trace["dropped"]
    assert dropped["reason"] == "cites another document's chunk"
    assert dropped["doc_id"] == "who-healthy-diet"
