from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.core.errors import DocumentError
from app.schemas.document import ChunkResponse, DocumentResponse
from app.services.ingestion.documents import DocumentService, validate_filename

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_service(request: Request) -> DocumentService:
    service = request.app.state.documents
    if service is None:
        raise DocumentError("database_unavailable", "Configure the document database first.", 503)
    return service


Service = Annotated[DocumentService, Depends(get_service)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
    },
)
async def upload(
    request: Request,
    service: Service,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
):
    name = validate_filename(filename)
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/pdf"
    ):
        raise DocumentError("unsupported_type", "Send the PDF body as application/pdf.", 415)
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise DocumentError(
            "unsupported_encoding", "Compressed request bodies are not supported.", 415
        )
    limit = service.settings.max_upload_bytes
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > limit:
            raise DocumentError("file_too_large", f"PDF exceeds the {limit}-byte limit.", 413)
        body.extend(part)
    if not body:
        raise DocumentError("empty_file", "The uploaded PDF is empty.")
    return await run_in_threadpool(service.ingest, name, bytes(body))


@router.get("", response_model=list[DocumentResponse])
def list_documents(service: Service, limit: Limit = 20, offset: Offset = 0):
    return service.list_documents(limit, offset)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, service: Service):
    return service.get(document_id)


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
def get_chunks(document_id: UUID, service: Service, limit: Limit = 20, offset: Offset = 0):
    return service.chunks(document_id, limit, offset)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, service: Service):
    service.remove(document_id)
    return Response(status_code=204)
