from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import DocumentError
from app.models.document import Chunk, Document
from app.models.embedding import ChunkEmbedding
from app.schemas.search import SearchHit, SearchRequest, SearchResponse
from app.services.embeddings.encoder import Encoder
from app.services.embeddings.indexing import encode_checked


class RetrievalService:
    def __init__(self, sessions: sessionmaker[Session], encoder: Encoder):
        self.sessions = sessions
        self.encoder = encoder

    def search(self, request: SearchRequest) -> SearchResponse:
        profile = self.encoder.profile
        complete = (
            select(Chunk.document_id)
            .outerjoin(
                ChunkEmbedding,
                and_(ChunkEmbedding.chunk_id == Chunk.id, ChunkEmbedding.profile_id == profile.id),
            )
            .group_by(Chunk.document_id)
            .having(func.count(Chunk.id) == func.count(ChunkEmbedding.chunk_id))
        )
        with self.sessions() as session:
            ready_count = session.scalar(
                select(func.count()).select_from(Document).where(Document.status == "ready")
            )
            indexed_count = session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.status == "ready", Document.id.in_(complete))
            )
        response = SearchResponse(
            profile_id=profile.id,
            model_name=profile.model_name,
            dimensions=profile.dimensions,
            ready_documents=ready_count,
            indexed_documents=indexed_count,
            unindexed_documents=ready_count - indexed_count,
            results=[],
        )
        if not ready_count:
            return response
        if not indexed_count:
            raise DocumentError(
                "index_required", "Index ready documents with the active model first.", 409
            )
        vector = encode_checked(self.encoder, [request.query])[0]
        distance = ChunkEmbedding.embedding.cosine_distance(vector).label("distance")
        with self.sessions() as session:
            rows = session.execute(
                select(Chunk, Document.filename, distance)
                .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    ChunkEmbedding.profile_id == profile.id,
                    Document.status == "ready",
                    Document.id.in_(complete),
                )
                .order_by(distance, Chunk.id)
                .limit(request.top_k)
            )
            response.results = [
                SearchHit(
                    **{
                        "id": chunk.id,
                        "document_id": chunk.document_id,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "text": chunk.text,
                    },
                    filename=filename,
                    cosine_distance=float(score),
                )
                for chunk, filename, score in rows
            ]
        return response
