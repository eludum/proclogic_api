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


def upgrade() -> None:
    op.add_column(
        "descriptions",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
    )

    # Every relationship load filters on kind alongside the parent key.
    op.create_index(
        "idx_descriptions_dossier_kind",
        "descriptions",
        ["dossier_reference_number", "kind"],
    )
    op.create_index("idx_descriptions_lot_kind", "descriptions", ["lot_id", "kind"])


def downgrade() -> None:
    op.drop_index("idx_descriptions_lot_kind", table_name="descriptions")
    op.drop_index("idx_descriptions_dossier_kind", table_name="descriptions")
    op.drop_column("descriptions", "kind")
