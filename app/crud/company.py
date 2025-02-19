import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.company_models import Company
from app.schemas.company_schemas import CompanySchema


def create_company(
    company: CompanySchema,
    session: Session,
) -> Optional[Company]:
    """Create a new company and add it to the database."""
    new_company = Company(
        vat_number=company.vat_number,
        name=company.name,
        email=company.email,
        summary_activities=company.summary_activities,
        accreditations=company.accreditations,
        interested_sectors=company.interested_sectors,
    )
    try:
        session.add(new_company)
        session.commit()
        return new_company
    except Exception as e:
        logging.error("Error creating company: %s", e)
        session.rollback()
        return None
    finally:
        session.close()


def get_company_by_vat_number(
    vat_number: str, session: Session
) -> Optional[Company]:
    """Retrieve a company by its VAT number."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_sectors),
                joinedload(Company.recommended_publications),
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
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_sectors),
                joinedload(Company.recommended_publications),
            )
            .all()
        )
    except Exception as e:
        logging.error("Error getting all companies: %s", e)
        return None
    finally:
        session.close()


def update_company(
    company_schema: CompanySchema,
    session: Session,
) -> Optional[Company]:
    """Update the details of an existing company."""
    company = session.query(Company).filter(Company.vat_number == company_schema.vat_number).first()
    if not company:
        logging.error(
            "Company with VAT number %s not found. Update failed.", company_schema.vat_number
        )
        return False

    company.vat_number = company_schema.vat_number
    company.name = company_schema.name
    company.email = company_schema.email
    company.summary_activities = company_schema.summary_activities
    company.accreditations = company_schema.accreditations
    company.max_publication_value = company_schema.max_publication_value
    company.interested_sectors = company_schema.interested_sectors

    try:
        session.commit()
        return company
    except Exception as e:
        session.rollback()
        logging.error("Error updating company: %s", e)
        return None


def delete_company(vat_number: str, session: Session) -> bool:
    """Delete a company by its VAT number."""
    company = session.query(Company).filter(Company.vat_number == vat_number).first()
    if not company:
        logging.error(
            "Company with VAT number %s not found. Deletion failed.", vat_number
        )
        return False
    try:
        session.delete(company)
        session.commit()
        return True
    except Exception as e:
        logging.error("Error deleting company: %s", e)
        session.rollback()
        return False
    finally:
        session.close()


def get_company_by_email(
    email: str, session: Session
) -> Optional[Company]:
    """Retrieve a company by its email."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_sectors),
                joinedload(Company.recommended_publications),
            )
            .filter(Company.email == email)
            .first()
        )
    except Exception as e:
        logging.error("Error getting company: %s", e)
        return None
    finally:
        session.close()
