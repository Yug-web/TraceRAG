from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import SearchHit


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20, strict=True)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    status: Literal["answered", "insufficient_evidence"]
    answer: str = Field(min_length=1, max_length=12000)
    citations: list[str] = Field(max_length=20)


class EvidenceSource(SearchHit):
    source_id: str


class AnswerResponse(GeneratedAnswer):
    sources: list[EvidenceSource]
    model: str | None
    retrieval_profile_id: str
    indexed_documents: int
    unindexed_documents: int
