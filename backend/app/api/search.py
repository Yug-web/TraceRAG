from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.errors import DocumentError
from app.schemas.search import IndexResult, IndexStatus, SearchRequest, SearchResponse
from app.services.embeddings.indexing import IndexingService
from app.services.retrieval.search import RetrievalService

router = APIRouter(prefix="/api", tags=["retrieval"])


def get_indexing(request: Request) -> IndexingService:
    if request.app.state.indexing is None:
        raise DocumentError("database_unavailable", "Configure the document database first.", 503)
    return request.app.state.indexing


def get_retrieval(request: Request) -> RetrievalService:
    if request.app.state.retrieval is None:
        raise DocumentError("database_unavailable", "Configure the document database first.", 503)
    return request.app.state.retrieval


@router.post("/documents/{document_id}/index", response_model=IndexResult)
def index_document(document_id: UUID, service: Annotated[IndexingService, Depends(get_indexing)]):
    return service.index(document_id)


@router.get("/documents/{document_id}/index-status", response_model=IndexStatus)
def index_status(document_id: UUID, service: Annotated[IndexingService, Depends(get_indexing)]):
    return service.status(document_id)


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, service: Annotated[RetrievalService, Depends(get_retrieval)]):
    return service.search(body)
