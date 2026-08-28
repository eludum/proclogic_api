"""add_searchable_content

Adds the Dutch full-text search column that both the award tools and the
publication tools use for recall.

Before this, award search (``build_search_filter`` in
``app/crud/publication_contract.py``) only ever matched organisation *names* via
correlated ILIKE subqueries -- it could not find "wegenwerken" in a title -- and
publication search was an unranked ``LIKE '%term%'`` over the ``descriptions``
table. Neither ever compared the actual text of a tender.

``searchable_content`` is a plain column populated by the application at ingest
(see ``build_searchable_content`` in ``app/util/publication_utils/searchable.py``)
and backfilled by ``scripts/backfill_searchable_content``. It deliberately is
NOT a generated column: Postgres generated columns may only reference the same
row, and this aggregates across ``descriptions`` and ``organisation_names``.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7g8
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column("searchable_content", sa.Text(), nullable=True),
    )

    # GIN index over the Dutch tsvector. The expression here must match the one
    # used in the query filters exactly, or Postgres will not use the index.
    op.execute(
        """
        CREATE INDEX idx_publications_searchable_content_fts
        ON publications
        USING GIN (to_tsvector('dutch', coalesce(searchable_content, '')))
        """
    )

    # Trigram index for the "contains" fallback used when a query has no
    # tsquery-able tokens (short strings, reference numbers, VAT numbers).
    # pg_trgm ships with Postgres but is not enabled by default.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX idx_publications_searchable_content_trgm
        ON publications
        USING GIN (searchable_content gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_publications_searchable_content_trgm")
    op.execute("DROP INDEX IF EXISTS idx_publications_searchable_content_fts")
    op.drop_column("publications", "searchable_content")
