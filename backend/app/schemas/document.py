from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    sha256: str
    size_bytes: int
    status: Literal["processing", "ready", "failed"]
    page_count: int
    chunk_count: int
    chunk_size: int
    chunk_overlap: int
    parser_version: str
    error_code: str | None
    error_message: str | None
    created_at: datetime


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    page_number: int
    chunk_index: int
    start_char: int
    end_char: int
    text: str
