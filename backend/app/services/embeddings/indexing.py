from dataclasses import asdict
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import DocumentError
from app.models.document import Chunk, Document
from app.models.embedding import ChunkEmbedding, EmbeddingProfileRow
from app.schemas.search import IndexResult, IndexStatus
from app.services.embeddings.encoder import Encoder, normalize


def encode_checked(encoder: Encoder, texts: list[str]) -> list[list[float]]:
    try:
        vectors = encoder.encode(texts)
        if len(vectors) != len(texts):
            raise ValueError("Embedding count mismatch")
        return [normalize(vector, encoder.profile.dimensions) for vector in vectors]
    except DocumentError:
        raise
    except Exception:
        raise DocumentError(
            "embedding_unavailable", "The embedding model returned invalid vectors.", 503
        ) from None


class IndexingService:
    def __init__(self, sessions: sessionmaker[Session], encoder: Encoder):
        self.sessions = sessions
        self.encoder = encoder

    def status(self, document_id: UUID) -> IndexStatus:
        profile_id = self.encoder.profile.id
        with self.sessions() as session:
            if session.get(Document, document_id) is None:
                raise DocumentError("not_found", "Document not found.", 404)
            total, indexed = session.execute(
                select(func.count(Chunk.id), func.count(ChunkEmbedding.chunk_id))
                .outerjoin(
                    ChunkEmbedding,
                    and_(
                        ChunkEmbedding.chunk_id == Chunk.id, ChunkEmbedding.profile_id == profile_id
                    ),
                )
                .where(Chunk.document_id == document_id)
            ).one()
        return IndexStatus(
            document_id=document_id,
            profile_id=profile_id,
            total_chunks=total,
            indexed_chunks=indexed,
            complete=total > 0 and total == indexed,
        )

    def index(self, document_id: UUID) -> IndexResult:
        profile = self.encoder.profile
        with self.sessions() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise DocumentError("not_found", "Document not found.", 404)
            if document.status != "ready":
                raise DocumentError(
                    "document_not_ready", "Extract the document before indexing.", 409
                )
            snapshot = list(
                session.execute(
                    select(Chunk.id, Chunk.text)
                    .where(Chunk.document_id == document_id)
                    .order_by(Chunk.chunk_index)
                )
            )
            existing = set(
                session.scalars(
                    select(ChunkEmbedding.chunk_id)
                    .join(Chunk)
                    .where(
                        Chunk.document_id == document_id, ChunkEmbedding.profile_id == profile.id
                    )
                )
            )
        missing = [
            (identifier, text) for identifier, text in snapshot if identifier not in existing
        ]
        # Inference occurs outside database transactions; no connection/row lock is held.
        vectors = encode_checked(self.encoder, [text for _, text in missing]) if missing else []
        with self.sessions.begin() as session:
            document = session.get(Document, document_id, with_for_update=True)
            if document is None:
                raise DocumentError("not_found", "Document was removed during indexing.", 404)
            current = list(
                session.execute(
                    select(Chunk.id, Chunk.text)
                    .where(Chunk.document_id == document_id)
                    .order_by(Chunk.chunk_index)
                )
            )
            if document.status != "ready" or current != snapshot:
                raise DocumentError("document_changed", "Document changed; retry indexing.", 409)
            session.execute(
                insert(EmbeddingProfileRow)
                .values(id=profile.id, **asdict(profile))
                .on_conflict_do_nothing(index_elements=["id"])
            )
            created = 0
            # Row lock serializes publication for this document; uniqueness also guards retries.
            for (identifier, _), vector in zip(missing, vectors, strict=True):
                result = session.execute(
                    insert(ChunkEmbedding)
                    .values(
                        chunk_id=identifier,
                        profile_id=profile.id,
                        dimensions=profile.dimensions,
                        embedding=vector,
                    )
                    .on_conflict_do_nothing(index_elements=["chunk_id", "profile_id"])
                    .returning(ChunkEmbedding.chunk_id)
                )
                created += int(result.scalar_one_or_none() is not None)
        status = self.status(document_id)
        return IndexResult(
            **status.model_dump(),
            created_embeddings=created,
            skipped_embeddings=status.indexed_chunks - created,
        )
