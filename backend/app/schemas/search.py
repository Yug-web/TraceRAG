from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import ChunkResponse


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20, strict=True)


class IndexStatus(BaseModel):
    document_id: UUID
    profile_id: str
    total_chunks: int
    indexed_chunks: int
    complete: bool


class IndexResult(IndexStatus):
    created_embeddings: int = Field(ge=0)
    skipped_embeddings: int = Field(ge=0)


class SearchHit(ChunkResponse):
    filename: str
    cosine_distance: float


class SearchResponse(BaseModel):
    profile_id: str
    model_name: str
    dimensions: int
    ready_documents: int
    indexed_documents: int
    unindexed_documents: int
    results: list[SearchHit]
