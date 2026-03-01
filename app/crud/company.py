import logging
from typing import List, Optional

from app.models.company_models import Company, Sector
from app.models.publication_models import (
    CompanyPublicationMatch,
    Dossier,
    Lot,
    Organisation,
    Publication,
)
from app.schemas.company_schemas import CompanySchema
from app.util.publication_utils.publication_converter import PublicationConverter
from sqlalchemy.orm import Session, joinedload


def create_company(
    company_schema: CompanySchema,
    session: Session,
) -> Optional[Company]:
    """Create a new company and add it to the database."""
    try:
        # First check if company already exists
        existing_company = (
            session.query(Company)
            .filter(Company.vat_number == company_schema.vat_number)
            .first()
        )

        if existing_company:
            logging.warning(
                f"Company with VAT number {company_schema.vat_number} already exists. Creation skipped."
            )
            return existing_company

        # Create the new company, setting defaults for any missing fields
        new_company = Company(
            vat_number=company_schema.vat_number,
            subscription=company_schema.subscription,
            number_of_employees=company_schema.number_of_employees or 1,
            name=company_schema.name,
            emails=company_schema.emails,
            summary_activities=company_schema.summary_activities,
            accreditations=company_schema.accreditations,
            max_publication_value=company_schema.max_publication_value,
            activity_keywords=company_schema.activity_keywords
            or PublicationConverter.extract_keywords(company_schema.summary_activities),
            operating_regions=company_schema.operating_regions or [],
        )

        # Create sectors
        if company_schema.interested_sectors:
            new_company.interested_sectors = [
                Sector(
                    sector=sector_schema.sector,
                    cpv_codes=sector_schema.cpv_codes,
                    company_vat_number=new_company.vat_number,
                )
                for sector_schema in company_schema.interested_sectors
            ]

        session.add(new_company)
        session.commit()

        session.refresh(new_company)
        return new_company
    except Exception as e:
        logging.error("Error creating company: %s", e)
        session.rollback()
        return None


def update_company(
    company_schema: dict,
    session: Session,
) -> Optional[Company]:
    """
    Update the details of an existing company with partial data.
    Only the fields provided in company_schema will be updated.
    """
    try:
        # Get the existing company
        company = (
            session.query(Company)
            .filter(Company.vat_number == company_schema["vat_number"])
            .first()
        )

        if not company:
            logging.error(
                "Company with VAT number %s not found. Update failed.",
                company_schema["vat_number"],
            )
            return None

        simple_fields = [
            "name",
            "subscription",
            "emails",
            "number_of_employees",
            "accreditations",
            "max_publication_value",
            "operating_regions",
            "summary_activities",
            "activity_keywords",
        ]

        for field in simple_fields:
            if field in company_schema:
                setattr(company, field, company_schema[field])

        if (
            "summary_activities" in company_schema
            and "activity_keywords" not in company_schema
        ):
            company.activity_keywords = PublicationConverter.extract_keywords(
                company_schema["summary_activities"]
            )

        if "interested_sectors" in company_schema:
            session.query(Sector).filter(
                Sector.company_vat_number == company.vat_number
            ).delete(synchronize_session=False)

            session.commit()

            if company_schema["interested_sectors"]:
                # Create new sector objects
                new_sectors = []
                for sector_data in company_schema["interested_sectors"]:
                    if isinstance(sector_data, dict):
                        sector = sector_data.get("sector")
                        cpv_codes = sector_data.get("cpv_codes", [])
                    else:
                        sector = getattr(sector_data, "sector", None)
                        cpv_codes = getattr(sector_data, "cpv_codes", [])

                    if sector:
                        new_sector = Sector(
                            sector=sector,
                            cpv_codes=cpv_codes,
                            company_vat_number=company.vat_number,
                        )
                        new_sectors.append(new_sector)
                        session.add(new_sector)

                company.interested_sectors = new_sectors

        session.commit()
        session.refresh(company)
        return company
    except Exception as e:
        session.rollback()
        logging.error("Error updating company: %s", e)
        return None


def append_emails_to_company(
    vat_number: str, emails: List[str], session: Session
) -> Optional[Company]:
    """
    Update the emails list for a company identified by VAT number.

    Args:
        vat_number: The VAT number of the company to update
        emails: List of email addresses to set for the company
        session: SQLAlchemy database session

    Returns:
        Updated Company object or None if the company wasn't found or update failed
    """
    try:
        # Get the existing company
        company = (
            session.query(Company).filter(Company.vat_number == vat_number).first()
        )

        if not company:
            logging.error(
                "Company with VAT number %s not found. Email update failed.",
                vat_number,
            )
            return None

        # Update the emails
        company.emails = company.emails + emails

        session.commit()
        session.refresh(company)
        return company
    except Exception as e:
        session.rollback()
        logging.error("Error updating company emails: %s", e)
        return None


def remove_email_from_company(
    vat_number: str, delete_email: str, session: Session
) -> Optional[Company]:
    """
    Update the emails list for a company identified by VAT number.

    Args:
        vat_number: The VAT number of the company to update
        emails: List of email addresses to set for the company
        session: SQLAlchemy database session

    Returns:
        Updated Company object or None if the company wasn't found or update failed
    """
    try:
        # Get the existing company
        company = (
            session.query(Company).filter(Company.vat_number == vat_number).first()
        )

        if not company:
            logging.error(
                "Company with VAT number %s not found. Email update failed.",
                vat_number,
            )
            return None

        # Update the emails
        company.emails = [email for email in company.emails if email != delete_email]

        session.commit()
        session.refresh(company)
        return company
    except Exception as e:
        session.rollback()
        logging.error("Error updating company emails: %s", e)
        return None


def get_company_by_vat_number(vat_number: str, session: Session, load_matches: bool = False) -> Optional[Company]:
    """Retrieve a company by its VAT number. Set load_matches=True to eager load publication matches."""
    try:
        query = session.query(Company).options(
            joinedload(Company.interested_sectors),
        )

        # Only load matches if explicitly requested (they can be thousands of records)
        if load_matches:
            query = query.options(joinedload(Company.publication_matches))

        return query.filter(Company.vat_number == vat_number).first()
    except Exception as e:
        logging.error("Error getting company: %s", e)
        return None


def get_company_by_email(email: str, session: Session, load_matches: bool = False) -> Optional[Company]:
    """Retrieve a company by its email. Set load_matches=True to eager load publication matches."""
    try:
        query = session.query(Company).options(
            joinedload(Company.interested_sectors),
        )

        # Only load matches if explicitly requested (they can be thousands of records)
        if load_matches:
            query = query.options(joinedload(Company.publication_matches))

        return query.filter(Company.emails.any(email)).first()  # Use .any() for array contains
    except Exception as e:
        logging.error("Error getting company: %s", e)
        return None


def get_company_recommended_publications(company_vat_number: str, session: Session):
    """Get all publications recommended for a company."""
    try:
        publication_ids = (
            session.query(CompanyPublicationMatch.publication_workspace_id)
            .filter(
                CompanyPublicationMatch.company_vat_number == company_vat_number,
                CompanyPublicationMatch.is_recommended == True,
            )
            .all()
        )
        publication_ids = [
            id[0] for id in publication_ids
        ]  # Extract IDs from result tuples

        if not publication_ids:
            return []

        # Query publications with all needed relationships eagerly loaded
        publications = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id.in_(publication_ids))
            .options(
                joinedload(Publication.dossier).joinedload(Dossier.titles),
                joinedload(Publication.dossier).joinedload(Dossier.descriptions),
                joinedload(Publication.organisation).joinedload(
                    Organisation.organisation_names
                ),
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.cpv_additional_codes),
                joinedload(Publication.company_matches),
                joinedload(Publication.lots).joinedload(Lot.descriptions),
                joinedload(Publication.lots).joinedload(Lot.titles),
            )
            .all()
        )

        return publications
    except Exception as e:
        logging.error("Error getting recommended publications: %s", e)
        return []


def get_company_saved_publications(company_vat_number: str, session: Session):
    """Get all publications saved by a company."""
    try:
        # Get publication IDs from matches
        publication_ids = (
            session.query(CompanyPublicationMatch.publication_workspace_id)
            .filter(
                CompanyPublicationMatch.company_vat_number == company_vat_number,
                CompanyPublicationMatch.is_saved == True,
            )
            .all()
        )

        publication_ids = [
            id[0] for id in publication_ids
        ]  # Extract IDs from result tuples

        if not publication_ids:
            return []

        # Query publications with all needed relationships eagerly loaded
        publications = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id.in_(publication_ids))
            .options(
                joinedload(Publication.dossier).joinedload(Dossier.titles),
                joinedload(Publication.dossier).joinedload(Dossier.descriptions),
                joinedload(Publication.organisation).joinedload(
                    Organisation.organisation_names
                ),
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.cpv_additional_codes),
                joinedload(Publication.company_matches),
                joinedload(Publication.lots).joinedload(Lot.descriptions),
                joinedload(Publication.lots).joinedload(Lot.titles),
            )
            .all()
        )

        return publications
    except Exception as e:
        logging.error("Error getting saved publications: %s", e)
        return []


def save_publication_for_company(
    company_vat_number: str, publication_workspace_id: str, session: Session
) -> bool:
    """Save a publication for a company."""
    try:
        match = (
            session.query(CompanyPublicationMatch)
            .filter(
                CompanyPublicationMatch.company_vat_number == company_vat_number,
                CompanyPublicationMatch.publication_workspace_id
                == publication_workspace_id,
            )
            .first()
        )

        if match:
            match.is_saved = True
            match.is_viewed = True
        else:
            # Create a new match if it doesn't exist
            match = CompanyPublicationMatch(
                company_vat_number=company_vat_number,
                publication_workspace_id=publication_workspace_id,
                is_saved=True,
                is_viewed=True,
                match_percentage=0.0,  # Default match percentage
                is_recommended=False,
            )
            session.add(match)

        session.commit()
        return True
    except Exception as e:
        logging.error("Error saving publication for company: %s", e)
        session.rollback()
        return False


def unsave_publication_for_company(
    company_vat_number: str, publication_workspace_id: str, session: Session
) -> bool:
    """Remove a publication from a company's saved list."""
    try:
        match = (
            session.query(CompanyPublicationMatch)
            .filter(
                CompanyPublicationMatch.company_vat_number == company_vat_number,
                CompanyPublicationMatch.publication_workspace_id
                == publication_workspace_id,
            )
            .first()
        )

        if match:
            match.is_saved = False
            session.commit()
            return True
        return False
    except Exception as e:
        logging.error("Error unsaving publication for company: %s", e)
        session.rollback()
        return False


def mark_publication_as_viewed(
    company_vat_number: str, publication_workspace_id: str, session: Session
) -> bool:
    """Mark a publication as viewed by a company."""
    try:
        match = (
            session.query(CompanyPublicationMatch)
            .filter(
                CompanyPublicationMatch.company_vat_number == company_vat_number,
                CompanyPublicationMatch.publication_workspace_id
                == publication_workspace_id,
            )
            .first()
        )

        # TODO: normally we dont need to check this
        if match:
            match.is_viewed = True
        else:
            # Create a new match if it doesn't exist
            match = CompanyPublicationMatch(
                company_vat_number=company_vat_number,
                publication_workspace_id=publication_workspace_id,
                is_saved=False,
                is_viewed=True,
                match_percentage=0.0,  # Default match percentage
                is_recommended=False,
            )
            session.add(match)

        session.commit()
        return True
    except Exception as e:
        logging.error("Error marking publication as viewed: %s", e)
        session.rollback()
        return False


def get_all_companies(session: Session, load_matches: bool = False) -> List[Company]:
    """Retrieve all companies. Set load_matches=True to eager load publication matches."""
    try:
        query = session.query(Company).options(
            joinedload(Company.interested_sectors),
        )

        # Only load matches if explicitly requested (they can be thousands of records per company)
        if load_matches:
            query = query.options(joinedload(Company.publication_matches))

        return query.all()
    except Exception as e:
        logging.error("Error getting all companies: %s", e)
        return []
