"""End-to-end: one golden question per category through /chat (implementation-plan.md, 8.6).

Needs the built index, the `embed` extra and GROQ_API_KEY, so these tests are marked
`e2e` and left out of the unit run (`pytest -m "not e2e"`). Run them with `make e2e`.

With E2E_BASE_URL set (e.g. http://localhost:8000) they call that running server, such
as the Docker stack; otherwise they start the real app in-process.
"""

import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from eval.golden import ANSWERABLE_CATEGORIES, GoldenCategory, GoldenEntry, load_golden

pytestmark = pytest.mark.e2e

GOLDEN = load_golden()
# The first question of each category.
CASES = {c: GOLDEN.by_category(c)[0] for c in GoldenCategory if GOLDEN.by_category(c)}


@pytest.fixture(scope="module")
def client() -> Iterator[Any]:
    base_url = os.environ.get("E2E_BASE_URL")
    if base_url:
        with httpx.Client(base_url=base_url, timeout=600) as c:
            if c.get("/health").status_code != 200:
                pytest.fail(f"{base_url}/health isn't ok: {c.get('/health').text}")
            yield c
        return

    from fastapi.testclient import TestClient

    from guidance_rag.api import create_app

    with TestClient(create_app()) as c:
        if c.get("/health").status_code != 200:
            pytest.fail(f"pipeline didn't load: {c.get('/health').json()}")
        yield c


@pytest.mark.parametrize("entry", CASES.values(), ids=[c.value for c in CASES])
def test_golden_question(client: Any, entry: GoldenEntry) -> None:
    res = client.post("/chat", json={"question": entry.question, "doc_filter": entry.doc_filter})
    assert res.status_code == 200, res.text
    body = res.json()
    cited = {s["doc_id"] for s in body["sections"]}
    context = f"{entry.id}: {body['status']}, cited {sorted(cited)}, trace {body['trace_id']}"

    assert body["status"] == entry.expected_status.value, context
    if entry.category in ANSWERABLE_CATEGORIES:
        assert body["refusal"] is None, context
        assert set(entry.expected_doc_ids) <= cited, context
        if entry.doc_filter:
            assert cited <= set(entry.doc_filter), context
        # Every claim cites a numbered citation, and every citation has its provenance.
        assert all(claim["citations"] for s in body["sections"] for claim in s["claims"])
        for c in body["citations"]:
            assert c["doc_title"] and c["publisher"] and c["year"], context
            assert c["url"].startswith("http"), context
    else:
        assert body["refusal"]["category"] == entry.expected_refusal, context
        assert not cited and not body["citations"], context
        if entry.category is GoldenCategory.NOT_IN_CORPUS:
            assert body["docs_searched"], context
