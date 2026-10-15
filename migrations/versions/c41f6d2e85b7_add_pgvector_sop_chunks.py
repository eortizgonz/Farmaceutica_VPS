"""add pgvector sop chunks

Revision ID: c41f6d2e85b7
Revises: bea76b57e29a
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "c41f6d2e85b7"
down_revision = "bea76b57e29a"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "sop_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_hash", "page", "chunk_index"),
    )
    op.create_index("ix_sop_chunks_document_hash", "sop_chunks", ["document_hash"])
    op.execute("CREATE INDEX ix_sop_chunks_embedding_hnsw ON sop_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade():
    op.drop_index("ix_sop_chunks_embedding_hnsw", table_name="sop_chunks")
    op.drop_index("ix_sop_chunks_document_hash", table_name="sop_chunks")
    op.drop_table("sop_chunks")
