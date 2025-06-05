# scripts/migrate_award_data.py
"""
Standalone script to migrate award data from PickleType to normalized tables.
Run this after the alembic migration if you need more complex data transformation.
"""

import logging
import pickle
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.config.settings import Settings

settings = Settings()


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("award_migration.log"), logging.StreamHandler()],
    )


def migrate_complex_award_data():
    """Handle complex award data migration cases"""

    engine = create_engine(settings.postgres_con_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Find publications that might have complex award data structures
        result = session.execute(
            text(
                """
                SELECT publication_workspace_id, award 
                FROM publications 
                WHERE award IS NOT NULL 
                AND contract_id IS NULL
            """
            )
        )

        publications = result.fetchall()
        logging.info(f"Found {len(publications)} publications needing award migration")

        for pub_id, award_data in publications:
            try:
                # Handle different award data formats
                parsed_award = parse_award_data(award_data)

                if parsed_award:
                    contract_id = create_contract_from_parsed_data(
                        session, parsed_award, pub_id
                    )

                    if contract_id:
                        # Update publication
                        session.execute(
                            text(
                                "UPDATE publications SET contract_id = :contract_id WHERE publication_workspace_id = :pub_id"
                            ),
                            {"contract_id": contract_id, "pub_id": pub_id},
                        )
                        logging.info(f"Successfully migrated publication {pub_id}")

            except Exception as e:
                logging.error(f"Failed to migrate publication {pub_id}: {e}")
                continue

        session.commit()
        logging.info("Award data migration completed successfully")

    except Exception as e:
        logging.error(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def parse_award_data(award_data):
    """Parse different formats of award data"""

    if award_data is None:
        return None

    try:
        # If it's already a dict
        if isinstance(award_data, dict):
            return award_data

        # If it's a JSON string
        if isinstance(award_data, str):
            try:
                return json.loads(award_data)
            except json.JSONDecodeError:
                logging.warning("Award data appears to be malformed JSON")
                return None

        # If it's pickled data
        if hasattr(award_data, "__dict__"):
            return award_data.__dict__

        # Try to unpickle if it's bytes
        if isinstance(award_data, bytes):
            try:
                return pickle.loads(award_data)
            except pickle.UnpicklingError:
                logging.warning("Could not unpickle award data")
                return None

        logging.warning(f"Unknown award data format: {type(award_data)}")
        return None

    except Exception as e:
        logging.error(f"Error parsing award data: {e}")
        return None


def create_contract_from_parsed_data(session, award_data, pub_id):
    """Create contract records from parsed award data"""

    try:
        # Extract basic contract info with defaults
        contract_id = (
            award_data.get("contract_id")
            or f"migrated_{pub_id}_{datetime.now().timestamp()}"
        )
        notice_id = award_data.get("notice_id") or f"notice_{pub_id}"

        # Handle organizations
        organizations = {}

        # Process each organization type
        for org_type in [
            "contracting_authority",
            "winning_publisher",
            "appeals_body",
            "service_provider",
        ]:
            org_data = award_data.get(org_type)
            if org_data:
                org_id = create_organization_record(session, org_data, org_type)
                organizations[f"{org_type}_id"] = org_id

        # Create contract record
        contract_data = {
            "contract_id": contract_id,
            "notice_id": notice_id,
            "internal_id": award_data.get("internal_id"),
            "issue_date": parse_date(award_data.get("issue_date")),
            "notice_type": award_data.get("notice_type"),
            "total_contract_amount": safe_float(
                award_data.get("total_contract_amount")
            ),
            "currency": award_data.get("currency", "EUR"),
            "lowest_publication_amount": safe_float(
                award_data.get("lowest_publication_amount")
            ),
            "highest_publication_amount": safe_float(
                award_data.get("highest_publication_amount")
            ),
            "number_of_publications_received": safe_int(
                award_data.get("number_of_publications_received")
            ),
            "number_of_participation_requests": safe_int(
                award_data.get("number_of_participation_requests")
            ),
            "electronic_auction_used": award_data.get("electronic_auction_used"),
            "dynamic_purchasing_system": award_data.get("dynamic_purchasing_system"),
            "framework_agreement": award_data.get("framework_agreement"),
            **organizations,  # Add organization IDs
        }

        # Remove None values
        contract_data = {k: v for k, v in contract_data.items() if v is not None}

        # Insert contract
        columns = ", ".join(contract_data.keys())
        placeholders = ", ".join([f":{k}" for k in contract_data.keys()])

        session.execute(
            text(f"INSERT INTO contracts ({columns}) VALUES ({placeholders})"),
            contract_data,
        )

        return contract_id

    except Exception as e:
        logging.error(f"Error creating contract: {e}")
        return None


def create_organization_record(session, org_data, org_type):
    """Create organization and related records"""

    if not org_data or not isinstance(org_data, dict):
        return None

    try:
        # Create address if present
        address_id = None
        if org_data.get("address"):
            address_id = create_address_record(session, org_data["address"])

        # Prepare organization data
        org_record = {
            "name": org_data.get("name", f"Unknown {org_type}"),
            "business_id": org_data.get("business_id"),
            "website": org_data.get("website"),
            "phone": org_data.get("phone"),
            "email": org_data.get("email"),
            "company_size": org_data.get("company_size"),
            "subcontracting": org_data.get("subcontracting"),
            "address_id": address_id,
        }

        # Remove None values
        org_record = {k: v for k, v in org_record.items() if v is not None}

        # Insert organization
        columns = ", ".join(org_record.keys())
        placeholders = ", ".join([f":{k}" for k in org_record.keys()])

        session.execute(
            text(
                f"INSERT INTO contract_organizations ({columns}) VALUES ({placeholders}) RETURNING id"
            ),
            org_record,
        )

        # Get the inserted ID
        org_id = session.execute(text("SELECT lastval()")).scalar()

        # Create contact persons
        if org_data.get("contact_persons"):
            create_contact_persons(session, org_data["contact_persons"], org_id)

        return org_id

    except Exception as e:
        logging.error(f"Error creating organization: {e}")
        return None


def create_address_record(session, address_data):
    """Create address record"""

    address_record = {
        "street": address_data.get("street"),
        "city": address_data.get("city"),
        "postal_code": address_data.get("postal_code"),
        "country": address_data.get("country"),
        "nuts_code": address_data.get("nuts_code"),
    }

    # Remove None values
    address_record = {k: v for k, v in address_record.items() if v is not None}

    if not address_record:
        return None

    # Insert address
    columns = ", ".join(address_record.keys())
    placeholders = ", ".join([f":{k}" for k in address_record.keys()])

    session.execute(
        text(f"INSERT INTO contract_addresses ({columns}) VALUES ({placeholders})"),
        address_record,
    )

    return session.execute(text("SELECT lastval()")).scalar()


def create_contact_persons(session, contacts_data, org_id):
    """Create contact person records"""

    if not contacts_data or not isinstance(contacts_data, list):
        return

    for contact in contacts_data:
        if not isinstance(contact, dict):
            continue

        contact_record = {
            "name": contact.get("name"),
            "job_title": contact.get("job_title"),
            "phone": contact.get("phone"),
            "email": contact.get("email"),
            "organization_id": org_id,
        }

        # Remove None values except organization_id
        contact_record = {
            k: v
            for k, v in contact_record.items()
            if v is not None or k == "organization_id"
        }

        if len(contact_record) > 1:  # More than just organization_id
            columns = ", ".join(contact_record.keys())
            placeholders = ", ".join([f":{k}" for k in contact_record.keys()])

            session.execute(
                text(
                    f"INSERT INTO contract_contact_persons ({columns}) VALUES ({placeholders})"
                ),
                contact_record,
            )


def parse_date(date_value):
    """Parse date from various formats"""

    if not date_value:
        return None

    if isinstance(date_value, datetime):
        return date_value

    if isinstance(date_value, str):
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
        except Exception:
            pass

    return None


def safe_float(value):
    """Safely convert to float"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value):
    """Safely convert to int"""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    setup_logging()
    logging.info("Starting award data migration...")
    migrate_complex_award_data()
    logging.info("Migration completed!")
