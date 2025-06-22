"""add_email_marketing

Revision ID: 939123525392
Revises: 9dc262f2c7ac
Create Date: 2025-06-15 02:41:10.330851

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "939123525392"
down_revision: Union[str, None] = "9dc262f2c7ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create contract_email_tracking table
    op.create_table(
        "contract_email_tracking",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.String(length=100), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=False),
        sa.Column(
            "email_type",
            sa.String(length=50),
            nullable=False,
            server_default="contract_winner_notification",
        ),
        sa.Column(
            "sent_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("is_delivered", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.contract_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for better performance
    op.create_index(
        "idx_contract_email_tracking_contract_id",
        "contract_email_tracking",
        ["contract_id"],
    )
    op.create_index(
        "idx_contract_email_tracking_sent_at", "contract_email_tracking", ["sent_at"]
    )
    op.create_index(
        "idx_contract_email_tracking_recipient",
        "contract_email_tracking",
        ["recipient_email"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index(
        "idx_contract_email_tracking_recipient", table_name="contract_email_tracking"
    )
    op.drop_index(
        "idx_contract_email_tracking_sent_at", table_name="contract_email_tracking"
    )
    op.drop_index(
        "idx_contract_email_tracking_contract_id", table_name="contract_email_tracking"
    )

    # Drop table
    op.drop_table("contract_email_tracking")
