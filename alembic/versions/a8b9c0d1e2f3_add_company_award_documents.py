"""add_company_award_documents

Files a company attaches to an award: their offer, the award letter they
received, whatever they want kept with it. Distinct from the BOSA annexes, which
are fetched live from the procurement API and belong to everyone.

The bytes live in Postgres because there is no object store in this stack and
pod filesystems are ephemeral. See app/models/company_award_document_models.py.

New table, so the index is built on an empty one and this migration stays
transactional -- no CONCURRENTLY, unlike c4d5e6f7a8b9 and d5e6f7a8b9c0.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.create_table(
        "company_award_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("award_entry_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_email", sa.String(length=320), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        # CASCADE: the files belong to the entry, so removing a company's data
        # for an award removes its uploads with it rather than orphaning them.
        sa.ForeignKeyConstraint(
            ["award_entry_id"], ["company_award_entries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_company_award_document_entry",
        "company_award_documents",
        ["award_entry_id"],
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.drop_index(
        "idx_company_award_document_entry", table_name="company_award_documents"
    )
    op.drop_table("company_award_documents")
