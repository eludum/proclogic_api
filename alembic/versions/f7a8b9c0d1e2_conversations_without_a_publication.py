"""conversations_without_a_publication

Lets a conversation exist without a tender behind it.

Procy queries the whole procurement database, so plenty of useful questions --
"wie wint de meeste wegenwerken in Limburg", "wat werd er vorig jaar gegund in
onze sector" -- are not about one publication. Until now every conversation
needed a publication_workspace_id, so the only way to reach Procy was from a
tender page, and the awards pages could not start a chat at all.

Existing rows are unaffected: they keep their publication, and the column simply
stops being required.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dropping NOT NULL is a catalogue change: no table rewrite, no scan.
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.alter_column(
        "conversations",
        "publication_workspace_id",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # Re-imposing NOT NULL would fail while general conversations exist, so drop
    # them first. They are chat history with no tender behind them; nothing else
    # references them.
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.execute("DELETE FROM conversations WHERE publication_workspace_id IS NULL")
    op.alter_column(
        "conversations",
        "publication_workspace_id",
        existing_type=sa.String(),
        nullable=False,
    )
