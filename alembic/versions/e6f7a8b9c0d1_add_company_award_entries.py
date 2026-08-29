"""add_company_award_entries

Company-supplied award data: values a customer fills in on a BOSA gunning that
was published incomplete, and awards they enter themselves. See
app/models/company_award_models.py for why this is a separate table rather than
columns on `contracts` -- in short, those rows are shared by every customer and
rewritten by the scraper.

Creating a new table, so no CONCURRENTLY here: the indexes are built on an empty
table and lock nothing anyone is reading. That also keeps this migration
transactional, unlike c4d5e6f7a8b9 and d5e6f7a8b9c0.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")

    op.create_table(
        "company_award_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_vat_number", sa.String(), nullable=False),
        sa.Column("created_by_email", sa.String(length=320), nullable=False),
        sa.Column("publication_workspace_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_document_name", sa.String(length=512), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("award_date", sa.DateTime(), nullable=True),
        sa.Column("winner", sa.String(length=512), nullable=True),
        sa.Column("buyer", sa.String(length=512), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("reference_number", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_vat_number"], ["companies.vat_number"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["publication_workspace_id"],
            ["publications.publication_workspace_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        # One overlay per company per BOSA award. Postgres treats NULLs as
        # distinct here, so a company can still create any number of its own
        # awards, which carry a NULL publication_workspace_id.
        sa.UniqueConstraint(
            "company_vat_number",
            "publication_workspace_id",
            name="uq_company_award_entry_scope",
        ),
    )

    op.create_index(
        "idx_company_award_entry_company",
        "company_award_entries",
        ["company_vat_number", "publication_workspace_id"],
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.drop_index("idx_company_award_entry_company", table_name="company_award_entries")
    op.drop_table("company_award_entries")
