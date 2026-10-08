"""LLM client wrapper (implementation-plan.md, 6.1), with fake transports."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import groq
import httpx
import pytest

from guidance_rag.llm import CachedLLM, GroqLLM, JsonRequest, LLMError, LLMResponse
from tests.fakes import FakeLLM

REQUEST = JsonRequest(
    model="openai/gpt-oss-120b",
    system="system",
    user="user",
    schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    schema_name="test",
)


def test_the_cache_returns_the_stored_response_on_the_second_call(tmp_path: Path) -> None:
    fake = FakeLLM('{"a": 1}')
    llm = CachedLLM(fake, cache_dir=tmp_path)

    first = llm.complete_json(REQUEST)
    second = llm.complete_json(REQUEST)

    assert first == second == LLMResponse('{"a": 1}', "stop")
    assert len(fake.requests) == 1
    assert (llm.hits, llm.misses) == (1, 1)


def test_the_cache_survives_a_restart_and_keys_on_the_whole_request(tmp_path: Path) -> None:
    CachedLLM(FakeLLM('{"a": 1}'), cache_dir=tmp_path).complete_json(REQUEST)

    fake = FakeLLM('{"b": 2}')
    llm = CachedLLM(fake, cache_dir=tmp_path)

    assert llm.complete_json(REQUEST).content == '{"a": 1}'
    other = JsonRequest(**{**REQUEST.__dict__, "user": "another question"})
    assert llm.complete_json(other).content == '{"b": 2}'


def test_incomplete_responses_are_not_cached(tmp_path: Path) -> None:
    fake = FakeLLM(LLMResponse('{"a":', "length"), '{"a": 1}')
    llm = CachedLLM(fake, cache_dir=tmp_path)

    assert not llm.complete_json(REQUEST).complete
    assert llm.complete_json(REQUEST).content == '{"a": 1}'
    assert len(fake.requests) == 2


def test_groq_request_uses_strict_structured_output() -> None:
    client = Mock()
    message = SimpleNamespace(content='{"a": 1}')
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")]
    )

    response = GroqLLM(client=client).complete_json(REQUEST)

    assert response == LLMResponse('{"a": 1}', "stop")
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["messages"][0] == {"role": "system", "content": "system"}
    assert kwargs["max_completion_tokens"] == REQUEST.max_tokens


def test_groq_errors_become_llm_errors() -> None:
    client = Mock()
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    client.chat.completions.create.side_effect = groq.APIConnectionError(request=request)

    with pytest.raises(LLMError):
        GroqLLM(client=client).complete_json(REQUEST)
