import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.company_models import Company, Sector
from app.models.publication_models import CompanyPublicationMatch, Dossier, Lot, Organisation, Publication
from app.schemas.company_schemas import CompanySchema
from app.util.publication_utils.publication_converter import PublicationConverter


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

        # Create the new company
        new_company = Company(
            vat_number=company_schema.vat_number,
            subscription=company_schema.subscription,
            name=company_schema.name,
            emails=company_schema.emails,
            summary_activities=company_schema.summary_activities,
            accreditations=company_schema.accreditations,
            max_publication_value=company_schema.max_publication_value,
            activity_keywords=PublicationConverter.extract_keywords(company_schema.activity_keywords),
            operating_regions=company_schema.operating_regions,
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
        return new_company
    except Exception as e:
        logging.error("Error creating company: %s", e)
        session.rollback()
        return None
    finally:
        session.close()


def get_company_by_vat_number(vat_number: str, session: Session) -> Optional[Company]:
    """Retrieve a company by its VAT number."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_sectors),
                joinedload(Company.publication_matches),
            )
            .filter(Company.vat_number == vat_number)
            .first()
        )
    except Exception as e:
        logging.error("Error getting company: %s", e)
        return None
    finally:
        session.close()


def get_all_companies(session: Session) -> List[Company]:
    """Retrieve all companies."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_sectors),
                joinedload(Company.publication_matches),
            )
            .all()
        )
    except Exception as e:
        logging.error("Error getting all companies: %s", e)
        return []
    finally:
        session.close()


def update_company(
    company_schema: CompanySchema,
    session: Session,
) -> Optional[Company]:
    """Update the details of an existing company."""
    try:
        company = (
            session.query(Company)
            .filter(Company.vat_number == company_schema.vat_number)
            .first()
        )

        if not company:
            logging.error(
                "Company with VAT number %s not found. Update failed.",
                company_schema.vat_number,
            )
            return None

        # Update basic fields
        company.name = company_schema.name
        company.subscription = (company_schema.subscription,)
        company.emails = company_schema.emails
        company.summary_activities = company_schema.summary_activities
        company.accreditations = company_schema.accreditations

        # Update new fields if present in schema
        if company_schema.max_publication_value:
            company.max_publication_value = company_schema.max_publication_value
        if company_schema.activity_keywords:
            company.activity_keywords = PublicationConverter.extract_keywords(
                company_schema.activity_keywords)
        if company_schema.operating_regions:
            company.operating_regions = company_schema.operating_regions

        # Update sectors - first remove existing ones
        if company_schema.interested_sectors:
            # Delete existing sectors
            session.query(Sector).filter(
                Sector.company_vat_number == company.vat_number
            ).delete(synchronize_session=False)

            # Add new sectors
            company.interested_sectors = [
                Sector(
                    sector=sector_schema.sector,
                    cpv_codes=sector_schema.cpv_codes,
                    company_vat_number=company.vat_number,
                )
                for sector_schema in company_schema.interested_sectors
            ]

        session.commit()
        return company
    except Exception as e:
        session.rollback()
        logging.error("Error updating company: %s", e)
        return None
    finally:
        session.close()


def delete_company(vat_number: str, session: Session) -> bool:
    """Delete a company by its VAT number."""
    try:
        # First delete all company-publication matches
        session.query(CompanyPublicationMatch).filter(
            CompanyPublicationMatch.company_vat_number == vat_number
        ).delete(synchronize_session=False)

        # Then delete the sectors
        session.query(Sector).filter(Sector.company_vat_number == vat_number).delete(
            synchronize_session=False
        )

        # Finally delete the company
        company = (
            session.query(Company).filter(Company.vat_number == vat_number).first()
        )
        if not company:
            logging.error(
                "Company with VAT number %s not found. Deletion failed.", vat_number
            )
            return False

        session.delete(company)
        session.commit()
        return True
    except Exception as e:
        logging.error("Error deleting company: %s", e)
        session.rollback()
        return False
    finally:
        session.close()


def get_company_by_email(email: str, session: Session) -> Optional[Company]:
    """Retrieve a company by its email."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_sectors),
                joinedload(Company.publication_matches),
            )
            .filter(Company.emails.any(email))  # Use .any() for array contains
            .first()
        )
    except Exception as e:
        logging.error("Error getting company: %s", e)
        return None
    finally:
        session.close()


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
        publication_ids = [id[0] for id in publication_ids]  # Extract IDs from result tuples
        
        if not publication_ids:
            return []
        
        # Query publications with all needed relationships eagerly loaded
        publications = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id.in_(publication_ids))
            .options(
                joinedload(Publication.dossier).joinedload(Dossier.titles),
                joinedload(Publication.dossier).joinedload(Dossier.descriptions),
                joinedload(Publication.organisation).joinedload(Organisation.organisation_names),
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
    finally:
        session.close()


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
        
        publication_ids = [id[0] for id in publication_ids]  # Extract IDs from result tuples
        
        if not publication_ids:
            return []
        
        # Query publications with all needed relationships eagerly loaded
        publications = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id.in_(publication_ids))
            .options(
                joinedload(Publication.dossier).joinedload(Dossier.titles),
                joinedload(Publication.dossier).joinedload(Dossier.descriptions),
                joinedload(Publication.organisation).joinedload(Organisation.organisation_names),
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
    finally:
        session.close()


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
    finally:
        session.close()


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
    finally:
        session.close()
