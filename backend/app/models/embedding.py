from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.document import Base


class EmbeddingProfileRow(Base):
    __tablename__ = "embedding_profiles"
    __table_args__ = (UniqueConstraint("id", "dimensions", name="profile_dimensions"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(255))
    revision: Mapped[str] = mapped_column(String(40))
    dimensions: Mapped[int]
    max_tokens: Mapped[int]
    preprocessing: Mapped[str] = mapped_column(String(64))


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "dimensions"],
            ["embedding_profiles.id", "embedding_profiles.dimensions"],
            ondelete="CASCADE",
        ),
        CheckConstraint("vector_dims(embedding) = dimensions", name="embedding_dimensions"),
    )

    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    dimensions: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
