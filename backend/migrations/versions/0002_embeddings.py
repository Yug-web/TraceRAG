"""Store model profiles and idempotent chunk embeddings."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "embedding_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("revision", sa.String(40), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("preprocessing", sa.String(64), nullable=False),
        sa.UniqueConstraint("id", "dimensions", name="profile_dimensions"),
    )
    op.create_table(
        "chunk_embeddings",
        sa.Column(
            "chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("profile_id", sa.String(64), primary_key=True),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "dimensions"],
            ["embedding_profiles.id", "embedding_profiles.dimensions"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("vector_dims(embedding) = dimensions", name="embedding_dimensions"),
    )
    op.create_index("ix_chunk_embeddings_profile_id", "chunk_embeddings", ["profile_id"])


def downgrade():
    op.drop_table("chunk_embeddings")
    op.drop_table("embedding_profiles")
    # The extension may be shared by other tables; never drop it on downgrade.
