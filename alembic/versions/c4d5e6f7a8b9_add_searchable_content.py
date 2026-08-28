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

The indexes are built CONCURRENTLY. ``run_migration()`` runs on every pod start,
and a plain CREATE INDEX on ``publications`` holds a lock that blocks writes for
the whole build -- which on a table this size would stall the scraper.

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


# The FTS expression must stay character-identical to SEARCHABLE_TSVECTOR in
# app/crud/fts.py, or Postgres will not use this index for those queries.
INDEXES = (
    (
        "idx_publications_searchable_content_fts",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_publications_searchable_content_fts ON publications "
        "USING GIN (to_tsvector('dutch', coalesce(searchable_content, '')))",
    ),
    (
        "idx_publications_searchable_content_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_publications_searchable_content_trgm ON publications "
        "USING GIN (searchable_content gin_trgm_ops)",
    ),
)


def _drop_if_invalid(connection, name: str) -> None:
    """Clear the wreckage of an interrupted CREATE INDEX CONCURRENTLY.

    A failed concurrent build leaves the index in place but marked invalid, and
    it stays that way: it is never used for queries, and a later
    ``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` sees the name and skips. Without
    this the index would be silently dead forever.
    """
    invalid = connection.execute(
        sa.text(
            "SELECT 1 FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
            "WHERE c.relname = :name AND NOT i.indisvalid"
        ),
        {"name": name},
    ).scalar()
    if invalid:
        connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))


def upgrade() -> None:
    # Bounded so a long-running query cannot make this ALTER queue for the
    # exclusive lock while every later query queues behind it. Adding a nullable
    # column with no default is metadata-only, so the lock is held very briefly.
    # SET LOCAL resets at commit, which matters because the autocommit block
    # below must not inherit a timeout that could abort a long index build.
    op.execute("SET LOCAL lock_timeout = '10s'")

    op.add_column(
        "publications",
        sa.Column("searchable_content", sa.Text(), nullable=True),
    )

    # pg_trgm ships with Postgres but is not enabled by default. Needed for the
    # substring-match arm of the search filter.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        connection = op.get_bind()
        for name, ddl in INDEXES:
            _drop_if_invalid(connection, name)
            connection.execute(sa.text(ddl))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        connection = op.get_bind()
        for name, _ddl in reversed(INDEXES):
            connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))

    op.execute("SET LOCAL lock_timeout = '10s'")
    op.drop_column("publications", "searchable_content")
