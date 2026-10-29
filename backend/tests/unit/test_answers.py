import asyncio
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from google.genai import errors, types

from app.core.config import Settings
from app.core.errors import DocumentError
from app.schemas.answer import AskRequest, EvidenceSource
from app.schemas.search import SearchResponse
from app.services.generation.answers import AnswerService
from app.services.generation.citations import validate_answer
from app.services.generation.provider import GeminiProvider


def source(text="Ocean currents carry heat."):
    return EvidenceSource(
        source_id="S1",
        id=uuid4(),
        document_id=uuid4(),
        filename="ocean.pdf",
        page_number=2,
        chunk_index=0,
        start_char=7,
        end_char=7 + len(text),
        text=text,
        cosine_distance=0.1,
    )


def output(**changes):
    return json.dumps(
        {"status": "answered", "answer": "Currents carry heat.", "citations": ["S1"], **changes}
    )


def test_valid_and_duplicate_citations():
    result = validate_answer(output(citations=["S1", "S1"]), [source()])
    assert result.citations == ["S1"]


@pytest.mark.parametrize(
    "raw,code",
    [
        ("not JSON", "invalid_model_output"),
        (output(citations=["S9"]), "invalid_citations"),
        (output(citations=[]), "invalid_citations"),
        (output(answer=" "), "invalid_model_output"),
        (output(extra="unexpected"), "invalid_model_output"),
        (output(status="insufficient_evidence"), "invalid_model_output"),
        ("x" * 32001, "invalid_model_output"),
    ],
)
def test_invalid_output_is_rejected(raw, code):
    with pytest.raises(DocumentError) as caught:
        validate_answer(raw, [source()])
    assert caught.value.code == code
    assert caught.value.status_code == 502


def test_abstention_replaces_untrusted_answer():
    result = validate_answer(
        output(status="insufficient_evidence", citations=[], answer="Unsupported assertion"),
        [source()],
    )
    assert "Unsupported" not in result.answer


def test_service_bounds_evidence_and_preserves_metadata():
    hit = source("a" * 1500)
    retrieval = Mock()
    retrieval.search.return_value = SearchResponse(
        profile_id="test",
        model_name="test",
        dimensions=3,
        ready_documents=1,
        indexed_documents=1,
        unindexed_documents=0,
        results=[hit],
    )
    provider = Mock(generate=AsyncMock(return_value=output()))
    service = AnswerService(retrieval, provider, Settings(_env_file=None, qa_context_chars=1000))
    result = asyncio.run(service.ask(AskRequest(question="Question?", top_k=1)))
    passage = result.sources[0]
    assert passage.document_id == hit.document_id and passage.page_number == 2
    assert passage.text == "a" * 1000 and passage.end_char == 1007
    prompt = json.loads(provider.generate.call_args.args[0])
    assert prompt == {
        "question": "Question?",
        "evidence": [{"source_id": "S1", "text": "a" * 1000}],
    }
    retrieval.search.assert_called_once()
    retrieval.search.return_value.results = []
    provider.generate.reset_mock()
    result = asyncio.run(service.ask(AskRequest(question="Question?")))
    assert result.status == "insufficient_evidence" and result.model is None
    provider.generate.assert_not_called()


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (httpx.ReadTimeout("secret"), 504, "provider_timeout"),
        (errors.APIError(429, {"error": {"message": "secret"}}), 429, "provider_rate_limited"),
        (errors.APIError(403, {"error": {"message": "secret"}}), 503, "provider_auth_failed"),
        (
            errors.APIError(503, {"error": {"message": "secret", "status": "UNAVAILABLE"}}),
            503,
            "provider_temporarily_unavailable",
        ),
        (errors.APIError(500, {"error": {"message": "secret"}}), 503, "provider_unavailable"),
        (RuntimeError("secret"), 503, "provider_unavailable"),
    ],
)
def test_provider_errors_are_safe(failure, status, code, caplog, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.generation.provider.asyncio.sleep", sleep)
    monkeypatch.setattr("app.services.generation.provider.random.uniform", lambda low, high: 0)
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    provider._request = AsyncMock(side_effect=failure)
    with pytest.raises(DocumentError) as caught:
        asyncio.run(provider.generate("private passage"))
    assert (caught.value.status_code, caught.value.code) == (status, code)
    assert "secret" not in caught.value.message
    assert "secret" not in caplog.text
    expected_calls = 2 if provider._is_transient(failure) else 1
    assert provider._request.await_count == expected_calls
    assert sleep.await_count == expected_calls - 1


def test_timeout_and_temporary_unavailability_are_distinct(monkeypatch):
    monkeypatch.setattr("app.services.generation.provider.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("app.services.generation.provider.random.uniform", lambda low, high: 0)
    timeout = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    timeout._request = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(DocumentError) as timed_out:
        asyncio.run(timeout.generate("private passage"))

    unavailable = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    unavailable._request = AsyncMock(
        side_effect=errors.APIError(
            503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}
        )
    )
    with pytest.raises(DocumentError) as unavailable_error:
        asyncio.run(unavailable.generate("private passage"))

    assert timed_out.value.code == "provider_timeout"
    assert unavailable_error.value.code == "provider_temporarily_unavailable"


def test_transient_failure_retries_once_then_succeeds(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.generation.provider.asyncio.sleep", sleep)
    monkeypatch.setattr("app.services.generation.provider.random.uniform", lambda low, high: 0.05)
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    provider._request = AsyncMock(
        side_effect=[
            errors.APIError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}),
            output(),
        ]
    )

    assert asyncio.run(provider.generate("private passage")) == output()
    assert provider._request.await_count == 2
    sleep.assert_awaited_once_with(0.3)


def test_exhausted_transient_retries_preserve_safe_error(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.generation.provider.asyncio.sleep", sleep)
    monkeypatch.setattr("app.services.generation.provider.random.uniform", lambda low, high: 0)
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    provider._request = AsyncMock(
        side_effect=errors.APIError(
            503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}
        )
    )

    with pytest.raises(DocumentError) as caught:
        asyncio.run(provider.generate("private passage"))

    assert caught.value.code == "provider_temporarily_unavailable"
    assert provider._request.await_count == 2
    sleep.assert_awaited_once_with(0.25)


def test_permanent_error_is_not_retried(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.generation.provider.asyncio.sleep", sleep)
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    provider._request = AsyncMock(
        side_effect=errors.APIError(
            404, {"error": {"message": "model not found", "status": "NOT_FOUND"}}
        )
    )

    with pytest.raises(DocumentError) as caught:
        asyncio.run(provider.generate("private passage"))

    assert caught.value.code == "provider_unavailable"
    provider._request.assert_awaited_once()
    sleep.assert_not_awaited()


def test_overall_deadline_stops_request_without_retry():
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    provider.settings.llm_timeout_seconds = 0.01

    async def never_finishes(prompt, key):
        await asyncio.Event().wait()

    provider._request = AsyncMock(side_effect=never_finishes)
    with pytest.raises(DocumentError) as caught:
        asyncio.run(provider.generate("private passage"))

    assert caught.value.code == "provider_timeout"
    provider._request.assert_awaited_once()


def test_missing_key_does_not_call_provider():
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key=None))
    provider._request = AsyncMock()
    with pytest.raises(DocumentError, match="Configure"):
        asyncio.run(provider.generate("question"))
    provider._request.assert_not_called()


def test_sdk_contract(monkeypatch):
    response = Mock(candidates=[Mock(finish_reason=types.FinishReason.STOP)], text=output())
    async_client = Mock(models=Mock(generate_content=AsyncMock(return_value=response)))
    client = Mock(aio=AsyncMock())
    client.aio.__aenter__.return_value = async_client
    factory = Mock(return_value=client)
    monkeypatch.setattr("app.services.generation.provider.genai.Client", factory)
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-key"))
    assert asyncio.run(provider.generate("evidence")) == output()
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    config = async_client.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert "citations" in config.response_json_schema["required"]
    client.close.assert_called_once()
