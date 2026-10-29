import hashlib
import logging
import unicodedata
from dataclasses import asdict
from uuid import UUID

import pypdf
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import DocumentError
from app.models.document import Chunk, Document, Page
from app.schemas.document import ChunkResponse, DocumentResponse
from app.services.ingestion.chunking import chunk_pages
from app.services.ingestion.pdf import parse_pdf

logger = logging.getLogger(__name__)


def validate_filename(filename: str) -> str:
    name = unicodedata.normalize("NFC", filename).strip()
    if (
        not name
        or len(name) > 255
        or any(char in name for char in "/\\:")
        or any(unicodedata.category(char).startswith("C") for char in name)
    ):
        raise DocumentError("invalid_filename", "Use a plain filename without paths or controls.")
    if not name.lower().endswith(".pdf"):
        raise DocumentError("unsupported_type", "Only .pdf files are supported.", 415)
    return name


class DocumentService:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def ingest(self, filename: str, data: bytes) -> DocumentResponse:
        if not data.startswith(b"%PDF-"):
            raise DocumentError("invalid_pdf", "The file does not have a PDF header.")
        with self.sessions.begin() as session:
            document = Document(
                filename=validate_filename(filename),
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                chunk_size=self.settings.chunk_size,
                chunk_overlap=self.settings.chunk_overlap,
                parser_version=f"pypdf/{pypdf.__version__}",
            )
            session.add(document)
            session.flush()
            document_id = document.id

        # Commit processing status first so another request can observe it.
        try:
            pages = parse_pdf(data, self.settings)
            chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        except Exception as exc:
            if isinstance(exc, DocumentError):
                error = exc
            else:
                logger.error("PDF ingestion failed: %s", type(exc).__name__)
                error = DocumentError("processing_failed", "Document processing failed.", 500)
            with self.sessions.begin() as session:
                document = session.get(Document, document_id, with_for_update=True)
                if document is not None:
                    document.status = "failed"
                    document.error_code = error.code
                    document.error_message = error.message
            error.document_id = str(document_id)
            raise error from None

        with self.sessions.begin() as session:
            document = session.get(Document, document_id, with_for_update=True)
            if document is None:
                raise DocumentError("not_found", "Document was removed during processing.", 404)
            session.add_all(
                Page(document_id=document_id, page_number=n, text=text)
                for n, text in enumerate(pages, start=1)
            )
            session.flush()
            session.add_all(
                Chunk(document_id=document_id, chunk_index=n, **asdict(chunk))
                for n, chunk in enumerate(chunks)
            )
            document.page_count = len(pages)
            document.chunk_count = len(chunks)
            document.status = "ready"
            session.flush()
            result = DocumentResponse.model_validate(document)
        return result

    def list_documents(self, limit: int, offset: int) -> list[DocumentResponse]:
        with self.sessions() as session:
            rows = session.scalars(
                select(Document)
                .order_by(Document.created_at.desc(), Document.id)
                .limit(limit)
                .offset(offset)
            )
            return [DocumentResponse.model_validate(row) for row in rows]

    def get(self, document_id: UUID) -> DocumentResponse:
        with self.sessions() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise DocumentError("not_found", "Document not found.", 404)
            return DocumentResponse.model_validate(document)

    def chunks(self, document_id: UUID, limit: int, offset: int) -> list[ChunkResponse]:
        with self.sessions() as session:
            if session.get(Document, document_id) is None:
                raise DocumentError("not_found", "Document not found.", 404)
            rows = session.scalars(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .order_by(Chunk.chunk_index)
                .limit(limit)
                .offset(offset)
            )
            return [ChunkResponse.model_validate(row) for row in rows]

    def remove(self, document_id: UUID) -> None:
        with self.sessions.begin() as session:
            result = session.execute(delete(Document).where(Document.id == document_id))
            if result.rowcount == 0:
                raise DocumentError("not_found", "Document not found.", 404)
