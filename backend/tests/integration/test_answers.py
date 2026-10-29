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


def test_document_to_answer_lifecycle_and_cleanup(qa_client):
    client, provider = qa_client
    identifier = upload(client, ["", "Ocean currents carry heat."], "ocean.pdf")

    document = client.get(f"/api/documents/{identifier}").json()
    assert document["id"] == identifier
    assert document["filename"] == "ocean.pdf"
    assert document["status"] == "ready"
    assert document["page_count"] == 2
    assert document["chunk_count"] == 1
    chunks = client.get(f"/api/documents/{identifier}/chunks").json()
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["document_id"] == identifier
    assert chunk["page_number"] == 2
    assert chunk["chunk_index"] == 0
    assert chunk["text"] == "Ocean currents carry heat."

    assert client.post("/api/ask", json={"question": "ocean"}).status_code == 409
    provider.generate.assert_not_called()

    index_response = client.post(f"/api/documents/{identifier}/index")
    assert index_response.status_code == 200, index_response.text
    indexing = index_response.json()
    assert indexing["document_id"] == identifier
    assert indexing["total_chunks"] == 1
    assert indexing["indexed_chunks"] == 1
    assert indexing["created_embeddings"] == 1
    assert indexing["skipped_embeddings"] == 0
    assert indexing["complete"] is True

    search_response = client.post("/api/search", json={"query": "ocean", "top_k": 1})
    assert search_response.status_code == 200, search_response.text
    search = search_response.json()
    assert search["indexed_documents"] == 1
    assert search["unindexed_documents"] == 0
    assert len(search["results"]) == 1
    hit = search["results"][0]
    for key, value in chunk.items():
        assert hit[key] == value
    assert hit["filename"] == "ocean.pdf"
    assert hit["page_number"] == 2

    response = client.post("/api/ask", json={"question": "ocean", "top_k": 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "answered"
    assert data["answer"] == "Ocean currents carry heat."
    assert data["citations"] == ["S1"]
    assert data["indexed_documents"] == 1
    assert data["unindexed_documents"] == 0
    source = data["sources"][0]
    for key, value in hit.items():
        assert source[key] == value
    assert source["source_id"] == "S1"
    prompt = json.loads(provider.generate.await_args.args[0])
    assert prompt == {
        "question": "ocean",
        "evidence": [{"source_id": "S1", "text": chunk["text"]}],
    }

    provider.generate.return_value = '{"status":"answered","answer":"bad","citations":["S99"]}'
    assert client.post("/api/ask", json={"question": "ocean"}).status_code == 502

    assert client.delete(f"/api/documents/{identifier}").status_code == 204
    assert client.get(f"/api/documents/{identifier}").status_code == 404
    assert client.get(f"/api/documents/{identifier}/chunks").status_code == 404
    assert client.get(f"/api/documents/{identifier}/index-status").status_code == 404
    after_delete = client.post("/api/search", json={"query": "ocean", "top_k": 1})
    assert after_delete.status_code == 200
    assert after_delete.json()["results"] == []
    assert after_delete.json()["indexed_documents"] == 0


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
