"""add_performance_indexes

Revision ID: b3c4d5e6f7g8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7g8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add composite index for publication filtering and sorting
    # Used in queries that filter by cpv_main_code and sort by publication_date
    op.create_index(
        "idx_publications_cpv_pubdate",
        "publications",
        ["cpv_main_code_code", "publication_date"],
    )

    # Add index on publication_date alone for sorting operations
    op.create_index(
        "idx_publications_publication_date",
        "publications",
        ["publication_date"],
    )

    # Add index on dossier_reference_number for foreign key lookups
    op.create_index(
        "idx_publications_dossier_ref",
        "publications",
        ["dossier_reference_number"],
    )

    # Add index on organisation_id for foreign key lookups
    op.create_index(
        "idx_publications_organisation_id",
        "publications",
        ["organisation_id"],
    )

    # Add composite index for company publication matches filtering
    # Used when getting recommended publications for a company
    op.create_index(
        "idx_match_company_recommended_pub",
        "company_publication_matches",
        ["company_vat_number", "is_recommended", "publication_workspace_id"],
    )

    # Add composite index for saved publications
    op.create_index(
        "idx_match_company_saved_pub",
        "company_publication_matches",
        ["company_vat_number", "is_saved", "publication_workspace_id"],
    )


def downgrade() -> None:
    # Drop indexes in reverse order
    op.drop_index("idx_match_company_saved_pub", table_name="company_publication_matches")
    op.drop_index("idx_match_company_recommended_pub", table_name="company_publication_matches")
    op.drop_index("idx_publications_organisation_id", table_name="publications")
    op.drop_index("idx_publications_dossier_ref", table_name="publications")
    op.drop_index("idx_publications_publication_date", table_name="publications")
    op.drop_index("idx_publications_cpv_pubdate", table_name="publications")
