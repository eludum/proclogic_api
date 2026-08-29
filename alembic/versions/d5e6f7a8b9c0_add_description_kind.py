"""add_description_kind

Gives `descriptions` a discriminator so a row's role is knowable.

Dossier.titles and Dossier.descriptions (and the same pair on Lot) were two
relationships over one foreign key with nothing to tell them apart, so both
returned every row belonging to the parent. get_publication_title therefore
returned whichever row happened to come last -- often the description. This is
visible today in /contracts, where award titles render as body text.

Existing rows get 'unknown', and the relationships treat 'unknown' as belonging
to BOTH collections. That is deliberate: it reproduces exactly the behaviour
those rows have today, so applying this migration changes nothing for existing
data. Only newly ingested rows are precise. Run
scripts/backfill_description_kind to classify the historical rows.

Indexes are built CONCURRENTLY -- see the note in c4d5e6f7a8b9.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every relationship load filters on kind alongside the parent key.
INDEXES = (
    (
        "idx_descriptions_dossier_kind",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_descriptions_dossier_kind "
        "ON descriptions (dossier_reference_number, kind)",
    ),
    (
        "idx_descriptions_lot_kind",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_descriptions_lot_kind "
        "ON descriptions (lot_id, kind)",
    ),
)


def _drop_if_invalid(connection, name: str) -> None:
    """Clear the wreckage of an interrupted CREATE INDEX CONCURRENTLY.

    Duplicated from c4d5e6f7a8b9 rather than imported: Alembic loads revision
    files by path, not as an importable package, and a migration that depends on
    another migration's code breaks the moment that file is edited.
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
    op.execute("SET LOCAL lock_timeout = '10s'")

    # A non-volatile default makes this metadata-only on PostgreSQL 11+: no
    # table rewrite, so the exclusive lock is held only momentarily.
    op.add_column(
        "descriptions",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
    )

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
    op.drop_column("descriptions", "kind")
