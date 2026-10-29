import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import DocumentError
from app.main import create_app
from tests.integration.test_retrieval import FakeEncoder, upload


@pytest.fixture
def qa_client(database_url, db_engine):
    provider = Mock(
        generate=AsyncMock(
            return_value=json.dumps(
                {"status": "answered", "answer": "Ocean currents carry heat.", "citations": ["S1"]}
            )
        )
    )
    app = create_app(Settings(_env_file=None, database_url=database_url), FakeEncoder(), provider)
    with TestClient(app) as client:
        yield client, provider


def test_qa_upload_index_answer_metadata(qa_client):
    client, provider = qa_client
    identifier = upload(client, ["", "Ocean currents carry heat."], "ocean.pdf")
    assert client.post("/api/ask", json={"question": "ocean"}).status_code == 409
    provider.generate.assert_not_called()
    assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    response = client.post("/api/ask", json={"question": "ocean", "top_k": 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["citations"] == ["S1"]
    source = data["sources"][0]
    original = client.get(f"/api/documents/{identifier}/chunks").json()[0]
    for key, value in original.items():
        assert source[key] == value
    assert source["filename"] == "ocean.pdf" and source["page_number"] == 2
    provider.generate.return_value = '{"status":"answered","answer":"bad","citations":["S99"]}'
    assert client.post("/api/ask", json={"question": "ocean"}).status_code == 502


def test_empty_corpus_and_request_validation(qa_client):
    client, provider = qa_client
    result = client.post("/api/ask", json={"question": "ocean"})
    assert result.json()["status"] == "insufficient_evidence"
    provider.generate.assert_not_called()
    for payload in (
        {"question": " "},
        {"question": "x" * 2001},
        {"question": "q", "top_k": 21},
        {"question": "q", "top_k": True},
    ):
        assert client.post("/api/ask", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            DocumentError("provider_timeout", "The answer provider timed out.", 504),
            504,
            "provider_timeout",
        ),
        (
            DocumentError(
                "provider_temporarily_unavailable",
                "The answer provider is temporarily unavailable.",
                503,
            ),
            503,
            "provider_temporarily_unavailable",
        ),
        (
            DocumentError("provider_rate_limited", "The answer provider is rate limited.", 429),
            429,
            "provider_rate_limited",
        ),
        (
            DocumentError("provider_auth_failed", "Provider credentials were rejected.", 503),
            503,
            "provider_auth_failed",
        ),
    ],
)
def test_provider_failures_have_stable_safe_api_responses(qa_client, error, status_code, code):
    client, provider = qa_client
    identifier = upload(client, ["Grounded benchmark evidence."], "evidence.pdf")
    assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    provider.generate.side_effect = error

    response = client.post("/api/ask", json={"question": "What is the evidence?"})

    assert response.status_code == status_code
    assert response.json()["detail"] == {
        "code": code,
        "message": error.message,
        "document_id": None,
    }
    assert "traceback" not in response.text.lower()
