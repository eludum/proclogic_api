"""remove_assistant_fields

Revision ID: a1b2c3d4e5f6
Revises: 939123525392
Create Date: 2025-10-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "939123525392"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove assistant_id and thread_id columns from conversations table
    op.drop_column("conversations", "assistant_id")
    op.drop_column("conversations", "thread_id")


def downgrade() -> None:
    # Add back assistant_id and thread_id columns if needed to rollback
    op.add_column(
        "conversations",
        sa.Column("assistant_id", sa.String(), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("thread_id", sa.String(), nullable=True)
    )
