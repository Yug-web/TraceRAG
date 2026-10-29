import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models.document import Chunk
from app.models.embedding import ChunkEmbedding
from app.services.embeddings.encoder import EmbeddingProfile
from tests.pdf_factory import make_pdf


class FakeEncoder:
    """Controlled vectors test ranking mechanics, not language understanding."""

    profile = EmbeddingProfile("synthetic-test-model", "a" * 40, 3, 256)

    def __init__(self):
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                [1.0, 0.0, 0.0]
                if "ocean" in lowered
                else [0.0, 1.0, 0.0]
                if "plant" in lowered
                else [0.0, 0.0, 1.0]
            )
        return vectors


@pytest.fixture
def retrieval_client(database_url, db_engine):
    encoder = FakeEncoder()
    app = create_app(Settings(_env_file=None, database_url=database_url), encoder=encoder)
    with TestClient(app) as client:
        yield client, encoder


def upload(client, pages, name="synthetic.pdf"):
    response = client.post(
        "/api/documents",
        params={"filename": name},
        content=make_pdf(pages),
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_index_retry_reuses_vectors_and_sources(retrieval_client, db_engine):
    client, encoder = retrieval_client
    identifier = upload(client, ["Ocean currents carry heat.", "Plants use sunlight."])
    before = client.get(f"/api/documents/{identifier}/chunks").json()
    assert client.get(f"/api/documents/{identifier}/index-status").json()["indexed_chunks"] == 0
    first = client.post(f"/api/documents/{identifier}/index")
    assert first.status_code == 200, first.text
    assert first.json()["created_embeddings"] == 2
    second = client.post(f"/api/documents/{identifier}/index").json()
    assert second["created_embeddings"] == 0 and second["skipped_embeddings"] == 2
    assert encoder.calls == 1
    assert client.get(f"/api/documents/{identifier}/chunks").json() == before
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 2


def test_search_ranking_and_metadata(retrieval_client):
    client, _ = retrieval_client
    ocean_id = upload(client, ["", "Ocean currents carry heat."], "ocean.pdf")
    plant_id = upload(client, ["Plants use sunlight."], "plants.pdf")
    for identifier in (ocean_id, plant_id):
        assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    result = client.post("/api/search", json={"query": "ocean", "top_k": 1})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["indexed_documents"] == 2
    hit = data["results"][0]
    source = client.get(f"/api/documents/{ocean_id}/chunks").json()[0]
    for key, value in source.items():
        assert hit[key] == value
    assert hit["filename"] == "ocean.pdf"
    assert hit["page_number"] == 2 and hit["chunk_index"] == 0
    assert hit["cosine_distance"] == pytest.approx(0, abs=1e-6)


def test_empty_and_unindexed_corpus(retrieval_client):
    client, encoder = retrieval_client
    assert client.post("/api/search", json={"query": "ocean"}).json()["results"] == []
    upload(client, ["Ocean currents carry heat."])
    response = client.post("/api/search", json={"query": "ocean"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "index_required"
    assert encoder.calls == 0


def test_partial_documents_are_excluded_and_coverage_reported(retrieval_client, db_engine):
    client, _ = retrieval_client
    partial = upload(client, ["Ocean one.", "Ocean two."])
    complete = upload(client, ["Plants grow."])
    for identifier in (partial, complete):
        assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    with Session(db_engine) as session, session.begin():
        chunk_id = session.scalar(
            select(Chunk.id).where(Chunk.document_id == UUID(partial)).limit(1)
        )
        session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.chunk_id == chunk_id))
    data = client.post("/api/search", json={"query": "ocean"}).json()
    assert data["indexed_documents"] == 1 and data["unindexed_documents"] == 1
    assert {row["document_id"] for row in data["results"]} == {complete}
    assert client.post(f"/api/documents/{partial}/index").json()["created_embeddings"] == 1


def test_embedding_failure_is_atomic_and_does_not_break_upload(
    retrieval_client, db_engine, monkeypatch
):
    client, encoder = retrieval_client
    identifier = upload(client, ["Ocean currents."])
    monkeypatch.setattr(encoder, "encode", lambda texts: [[float("nan")]] * len(texts))
    assert client.post(f"/api/documents/{identifier}/index").status_code == 503
    assert client.get(f"/api/documents/{identifier}").json()["status"] == "ready"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0
    assert client.get("/api/health").status_code == 200


def test_profile_switch_requires_indexing(retrieval_client, database_url):
    client, _ = retrieval_client
    identifier = upload(client, ["Ocean currents."])
    assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    other = FakeEncoder()
    other.profile = EmbeddingProfile("synthetic-test-model", "b" * 40, 3, 256)
    with TestClient(
        create_app(Settings(_env_file=None, database_url=database_url), other)
    ) as second:
        assert second.post("/api/search", json={"query": "ocean"}).status_code == 409
        assert second.post(f"/api/documents/{identifier}/index").json()["created_embeddings"] == 1
        assert second.post("/api/search", json={"query": "ocean"}).status_code == 200


def test_delete_cascades_vectors(retrieval_client, db_engine):
    client, _ = retrieval_client
    identifier = upload(client, ["Ocean currents."])
    assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    assert client.delete(f"/api/documents/{identifier}").status_code == 204
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0


def test_concurrent_retries_do_not_duplicate(retrieval_client, db_engine, monkeypatch):
    client, encoder = retrieval_client
    identifier = UUID(upload(client, ["Ocean currents."]))
    barrier = threading.Barrier(2, timeout=10)
    original = encoder.encode

    def synchronized(texts):
        barrier.wait()
        return original(texts)

    monkeypatch.setattr(encoder, "encode", synchronized)
    service = client.app.state.indexing
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(service.index, [identifier, identifier]))
    assert sum(result.created_embeddings for result in results) == 1
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 1


def test_deleted_while_encoding_does_not_resurrect(retrieval_client, monkeypatch):
    client, encoder = retrieval_client
    identifier = upload(client, ["Ocean currents."])
    original = encoder.encode

    def remove(texts):
        client.delete(f"/api/documents/{identifier}")
        return original(texts)

    monkeypatch.setattr(encoder, "encode", remove)
    assert client.post(f"/api/documents/{identifier}/index").status_code == 404


def test_endpoint_validation_and_missing_documents(retrieval_client):
    client, _ = retrieval_client
    for body in ({"query": " "}, {"query": "a" * 2001}, {"query": "ok", "top_k": 21}):
        assert client.post("/api/search", json=body).status_code == 422
    assert client.post(f"/api/documents/{uuid4()}/index").status_code == 404


def test_embedding_publication_rolls_back_on_database_failure(retrieval_client, db_engine):
    client, _ = retrieval_client
    identifier = upload(client, ["Ocean currents.", "Plants grow."])
    engine = client.app.state.indexing.sessions.kw["bind"]
    inserts = 0

    def fail_second(connection, cursor, statement, parameters, context, executemany):
        nonlocal inserts
        if statement.startswith("INSERT INTO chunk_embeddings"):
            inserts += 1
            if inserts == 2:
                raise OperationalError("synthetic failure", {}, Exception("test"))

    event.listen(engine, "before_cursor_execute", fail_second)
    try:
        assert client.post(f"/api/documents/{identifier}/index").status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", fail_second)
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0
    assert client.get(f"/api/documents/{identifier}").json()["status"] == "ready"


def test_search_handles_unavailable_model(retrieval_client, monkeypatch):
    client, encoder = retrieval_client
    identifier = upload(client, ["Ocean currents."])
    assert client.post(f"/api/documents/{identifier}/index").status_code == 200
    monkeypatch.setattr(encoder, "encode", lambda texts: [[0, 0, 0]])
    response = client.post("/api/search", json={"query": "ocean"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "embedding_unavailable"
