from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import DocumentError
from app.main import create_app
from app.models.document import Chunk, Document, Page
from tests.pdf_factory import make_pdf


def upload(client, data=None, filename="research.pdf", content_type="application/pdf"):
    return client.post(
        "/api/documents",
        params={"filename": filename},
        content=make_pdf(["Some evidence text."]) if data is None else data,
        headers={"Content-Type": content_type},
    )


def test_document_lifecycle_and_cascade(document_client, db_engine):
    client = document_client
    response = upload(client, make_pdf(["Evidence on page one.", "", "Evidence on page three."]))
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["status"] == "ready"
    assert document["page_count"] == 3
    identifier = document["id"]
    assert client.get(f"/api/documents/{identifier}").json() == document
    assert client.get("/api/documents").json() == [document]
    chunks = client.get(f"/api/documents/{identifier}/chunks").json()
    assert len(chunks) == document["chunk_count"]
    assert {chunk["page_number"] for chunk in chunks} == {1, 3}
    with Session(db_engine) as session:
        for chunk in chunks:
            page = session.get(Page, (UUID(identifier), chunk["page_number"]))
            assert page.text[chunk["start_char"] : chunk["end_char"]] == chunk["text"]
    assert client.delete(f"/api/documents/{identifier}").status_code == 204
    assert client.get(f"/api/documents/{identifier}").status_code == 404
    with Session(db_engine) as session:
        for model in (Document, Page, Chunk):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    "data,code",
    [
        (b"%PDF-1.7\nbroken", "invalid_pdf"),
        (make_pdf([""]), "no_text"),
        (make_pdf(["text"], password="password"), "encrypted_pdf"),
    ],
)
def test_failed_processing_is_persisted_without_chunks(document_client, data, code):
    response = upload(document_client, data)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == code
    identifier = detail["document_id"]
    document = document_client.get(f"/api/documents/{identifier}").json()
    assert document["status"] == "failed"
    assert document["error_code"] == code
    assert document_client.get(f"/api/documents/{identifier}/chunks").json() == []


@pytest.mark.parametrize(
    "filename,content_type,data,status",
    [
        ("../escape.pdf", "application/pdf", b"%PDF-", 422),
        ("a.txt", "application/pdf", b"%PDF-", 415),
        ("a.pdf", "text/plain", b"%PDF-", 415),
        ("a.pdf", "application/pdf", b"", 422),
        ("a.pdf", "application/pdf", b"not a PDF", 422),
    ],
)
def test_rejected_upload_creates_no_record(document_client, filename, content_type, data, status):
    response = upload(document_client, data, filename, content_type)
    assert response.status_code == status
    assert document_client.get("/api/documents").json() == []


def test_stream_size_limit_without_content_length(database_url, db_engine):
    settings = Settings(_env_file=None, database_url=database_url, max_upload_bytes=8)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/documents?filename=a.pdf",
            content=iter([b"%PDF-", b"12345"]),
            headers={"Content-Type": "application/pdf"},
        )
        assert response.status_code == 413
        assert client.get("/api/documents").json() == []


def test_processing_status_is_visible_before_completion(document_client, monkeypatch):
    def parse(data, settings):
        rows = document_client.get("/api/documents").json()
        assert len(rows) == 1 and rows[0]["status"] == "processing"
        return ["Processed text"]

    monkeypatch.setattr("app.services.ingestion.documents.parse_pdf", parse)
    assert upload(document_client).json()["status"] == "ready"


def test_timeout_leaves_failed_record(document_client, monkeypatch):
    def parse(data, settings):
        raise DocumentError("parse_timeout", "PDF processing timed out.")

    monkeypatch.setattr("app.services.ingestion.documents.parse_pdf", parse)
    assert upload(document_client).json()["detail"]["code"] == "parse_timeout"
    assert document_client.get("/api/documents").json()[0]["status"] == "failed"


def test_delete_during_processing_does_not_recreate_document(document_client, monkeypatch):
    def parse(data, settings):
        identifier = document_client.get("/api/documents").json()[0]["id"]
        assert document_client.delete(f"/api/documents/{identifier}").status_code == 204
        return ["text"]

    monkeypatch.setattr("app.services.ingestion.documents.parse_pdf", parse)
    assert upload(document_client).status_code == 404
    assert document_client.get("/api/documents").json() == []


def test_pagination_and_missing_ids(document_client):
    for _ in range(3):
        assert upload(document_client).status_code == 201
    first = document_client.get("/api/documents?limit=2").json()
    second = document_client.get("/api/documents?limit=2&offset=2").json()
    assert len(first) == 2 and len(second) == 1
    assert len({row["id"] for row in first + second}) == 3
    assert document_client.get("/api/documents?limit=101").status_code == 422
    assert document_client.delete(f"/api/documents/{uuid4()}").status_code == 404


def test_database_not_configured():
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/documents").status_code == 503


def test_migration_round_trip(database_url, db_engine):
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


def test_failed_publication_rolls_back_all_source_text(document_client, db_engine):
    def reject_chunk(mapper, connection, target):
        raise IntegrityError("sensitive SQL", {"text": "private passage"}, Exception("failure"))

    event.listen(Chunk, "before_insert", reject_chunk)
    try:
        response = upload(document_client)
    finally:
        event.remove(Chunk, "before_insert", reject_chunk)
    assert response.status_code == 503
    assert "private passage" not in response.text
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Page)) == 0
        assert session.scalar(select(func.count()).select_from(Chunk)) == 0
        # A database outage may leave a recoverable processing record, never ready.
        assert session.scalar(select(Document.status)) == "processing"


def test_unexpected_parser_error_is_safe_and_persisted(document_client, monkeypatch, caplog):
    def parse(data, settings):
        raise RuntimeError("private document contents")

    monkeypatch.setattr("app.services.ingestion.documents.parse_pdf", parse)
    response = upload(document_client)
    assert response.status_code == 500
    assert "private document contents" not in response.text
    assert "private document contents" not in caplog.text
    assert document_client.get("/api/documents").json()[0]["status"] == "failed"


def test_document_survives_a_new_app_instance(document_client, database_url):
    identifier = upload(document_client).json()["id"]
    with TestClient(create_app(Settings(_env_file=None, database_url=database_url))) as other:
        assert other.get(f"/api/documents/{identifier}").json()["status"] == "ready"
