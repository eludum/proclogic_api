"""add_contract_award_models

Revision ID: 9dc262f2c7ac
Revises: 8a03694dc199
Create Date: 2025-06-05 22:24:22.328694

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import text
import json
import logging
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = "9dc262f2c7ac"
down_revision: Union[str, None] = "8a03694dc199"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1. Create new contract award tables
    create_contract_award_tables()

    # 2. Add contract_id column to publications (BEFORE migration)
    add_contract_id_column()

    # 3. Migrate existing data
    migrate_award_data()

    # 4. Remove old award column and add foreign key constraint
    cleanup_old_schema()


def downgrade():
    # Restore the old schema
    op.add_column("publications", sa.Column("award", sa.PickleType(), nullable=True))

    # Drop the foreign key first
    op.drop_constraint(
        "fk_publications_contract_id", "publications", type_="foreignkey"
    )
    op.drop_column("publications", "contract_id")

    # Drop the new tables in reverse order
    op.drop_table("contracts")
    op.drop_table("contract_contact_persons")
    op.drop_table("contract_organizations")
    op.drop_table("contract_addresses")


def create_contract_award_tables():
    """Create the new contract award tables"""

    # Contract addresses table
    op.create_table(
        "contract_addresses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("nuts_code", sa.String(length=10), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Contract organizations table
    op.create_table(
        "contract_organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("business_id", sa.String(length=50), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("company_size", sa.String(length=50), nullable=True),
        sa.Column("subcontracting", sa.String(length=100), nullable=True),
        sa.Column("address_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["address_id"],
            ["contract_addresses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Contract contact persons table
    op.create_table(
        "contract_contact_persons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["contract_organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Contracts table
    op.create_table(
        "contracts",
        sa.Column("contract_id", sa.String(length=100), nullable=False),
        sa.Column("notice_id", sa.String(length=100), nullable=False),
        sa.Column("internal_id", sa.String(length=255), nullable=True),
        sa.Column("issue_date", sa.DateTime(), nullable=True),
        sa.Column("notice_type", sa.String(length=100), nullable=True),
        sa.Column("total_contract_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("lowest_publication_amount", sa.Float(), nullable=True),
        sa.Column("highest_publication_amount", sa.Float(), nullable=True),
        sa.Column("number_of_publications_received", sa.Integer(), nullable=True),
        sa.Column("number_of_participation_requests", sa.Integer(), nullable=True),
        sa.Column("electronic_auction_used", sa.Boolean(), nullable=True),
        sa.Column("dynamic_purchasing_system", sa.String(length=50), nullable=True),
        sa.Column("framework_agreement", sa.String(length=50), nullable=True),
        sa.Column("contracting_authority_id", sa.Integer(), nullable=True),
        sa.Column("winning_publisher_id", sa.Integer(), nullable=True),
        sa.Column("appeals_body_id", sa.Integer(), nullable=True),
        sa.Column("service_provider_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["appeals_body_id"],
            ["contract_organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["contracting_authority_id"],
            ["contract_organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_provider_id"],
            ["contract_organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["winning_publisher_id"],
            ["contract_organizations.id"],
        ),
        sa.PrimaryKeyConstraint("contract_id"),
        sa.UniqueConstraint("notice_id", name="uq_contract_notice_id"),
    )


def add_contract_id_column():
    """Add the contract_id column to publications table"""
    op.add_column(
        "publications", sa.Column("contract_id", sa.String(length=100), nullable=True)
    )


def migrate_award_data():
    """Migrate existing award data from PickleType to new normalized tables"""

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Get all publications with award data
        result = session.execute(
            text(
                "SELECT publication_workspace_id, award FROM publications WHERE award IS NOT NULL"
            )
        )

        publications_with_awards = result.fetchall()
        print(
            f"Found {len(publications_with_awards)} publications with award data to migrate"
        )

        successful_migrations = 0
        failed_migrations = 0

        for pub_id, award_data in publications_with_awards:
            # Use a savepoint for each publication to handle individual failures
            savepoint = session.begin_nested()

            try:
                if award_data is None:
                    continue

                # Handle different types of pickled data
                parsed_award = unpickle_award_data(award_data)

                if parsed_award is None:
                    print(f"Could not parse award data for publication {pub_id}")
                    savepoint.rollback()
                    failed_migrations += 1
                    continue

                # Create contract record from parsed award data
                contract_id = create_contract_from_award(session, parsed_award, pub_id)

                if contract_id:
                    # Update publication to reference the new contract
                    session.execute(
                        text(
                            "UPDATE publications SET contract_id = :contract_id WHERE publication_workspace_id = :pub_id"
                        ),
                        {"contract_id": contract_id, "pub_id": pub_id},
                    )
                    savepoint.commit()
                    successful_migrations += 1
                    print(f"✓ Migrated award data for publication {pub_id}")
                else:
                    savepoint.rollback()
                    failed_migrations += 1
                    print(f"✗ Failed to create contract for publication {pub_id}")

            except Exception as e:
                print(f"✗ Error migrating award data for publication {pub_id}: {e}")
                savepoint.rollback()
                failed_migrations += 1
                continue

        session.commit()
        print(
            f"Award data migration completed: {successful_migrations} successful, {failed_migrations} failed"
        )

    except Exception as e:
        print(f"Error during award data migration: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def unpickle_award_data(award_data):
    """Properly unpickle award data from various formats"""
    import pickle

    try:
        # If it's already a dict, return it
        if isinstance(award_data, dict):
            return award_data

        # If it's a memoryview (binary data from PickleType)
        if isinstance(award_data, memoryview):
            try:
                # Convert memoryview to bytes and unpickle
                unpickled = pickle.loads(award_data.tobytes())
                return unpickled
            except Exception as e:
                print(f"Error unpickling memoryview: {e}")
                return None

        # If it's bytes
        if isinstance(award_data, bytes):
            try:
                unpickled = pickle.loads(award_data)
                return unpickled
            except Exception as e:
                print(f"Error unpickling bytes: {e}")
                return None

        # If it's a string (JSON)
        if isinstance(award_data, str):
            try:
                import json

                return json.loads(award_data)
            except Exception as e:
                print(f"Error parsing JSON string: {e}")
                return None

        # If it has __dict__ attribute (object)
        if hasattr(award_data, "__dict__"):
            return award_data.__dict__

        print(f"Unknown award data type: {type(award_data)}")
        return None

    except Exception as e:
        print(f"Error in unpickle_award_data: {e}")
        return None


def create_contract_from_award(session, award_dict, pub_id):
    """Create contract from award data structure"""

    try:
        # Handle case where award_dict might not be a dict
        if not isinstance(award_dict, dict):
            print(f"Award data is not a dict: {type(award_dict)}")
            return None

        # Create winning publisher organization if winner exists
        winning_publisher_id = None
        winner = award_dict.get("winner")
        if winner and isinstance(winner, str):
            winning_publisher_id = create_organization(session, winner)

        # Create service provider organizations for suppliers
        service_provider_id = None
        suppliers = award_dict.get("suppliers", [])
        if suppliers and isinstance(suppliers, list) and len(suppliers) > 0:
            # For simplicity, use the first supplier as service provider
            first_supplier = suppliers[0]
            if isinstance(first_supplier, dict) and first_supplier.get("name"):
                service_provider_id = create_organization(
                    session, first_supplier["name"]
                )

        # Generate unique contract ID with timestamp to avoid duplicates
        timestamp = int(datetime.now().timestamp())
        contract_id = f"award_{pub_id}_{timestamp}"
        notice_id = f"notice_{pub_id}_{timestamp}"

        # Get contract value safely
        contract_value = award_dict.get("value")
        if contract_value is not None:
            try:
                contract_value = float(contract_value)
            except (ValueError, TypeError):
                contract_value = None

        # Insert contract - simplified query to avoid constraint issues
        session.execute(
            text(
                """
                INSERT INTO contracts (
                    contract_id, notice_id, notice_type, total_contract_amount, 
                    currency, winning_publisher_id, service_provider_id
                ) VALUES (
                    :contract_id, :notice_id, :notice_type, :total_contract_amount,
                    :currency, :winning_publisher_id, :service_provider_id
                )
            """
            ),
            {
                "contract_id": contract_id,
                "notice_id": notice_id,
                "notice_type": "Contract Award Notice",
                "total_contract_amount": contract_value,
                "currency": "EUR",
                "winning_publisher_id": winning_publisher_id,
                "service_provider_id": service_provider_id,
            },
        )

        return contract_id

    except Exception as e:
        print(f"Error creating contract: {e}")
        # Re-raise to trigger savepoint rollback
        raise


def create_organization(session, org_name):
    """Create a simple organization record with just a name"""

    if not org_name or not isinstance(org_name, str):
        return None

    # Clean the organization name
    org_name = org_name.strip()
    if len(org_name) > 255:  # Respect the column length limit
        org_name = org_name[:255]

    try:
        # Check if organization already exists to avoid duplicates
        existing = session.execute(
            text("SELECT id FROM contract_organizations WHERE name = :name LIMIT 1"),
            {"name": org_name},
        ).fetchone()

        if existing:
            return existing[0]

        # Create organization with minimal data
        session.execute(
            text(
                """
                INSERT INTO contract_organizations (name) VALUES (:name)
            """
            ),
            {"name": org_name},
        )

        # Get the inserted organization ID
        org_id = session.execute(text("SELECT lastval()")).scalar()
        return org_id

    except Exception as e:
        print(f"Error creating organization '{org_name}': {e}")
        # Re-raise to trigger savepoint rollback
        raise


def cleanup_old_schema():
    """Add foreign key constraint and remove old award column"""

    # Create foreign key constraint to the correct table
    op.create_foreign_key(
        "fk_publications_contract_id",
        "publications",
        "contracts",
        ["contract_id"],
        ["contract_id"],
    )

    # Drop the old award column
    op.drop_column("publications", "award")
