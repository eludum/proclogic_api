import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.config.postgres import get_session
from app.models.publication_models import Company, CPVCode


def create_company(
    company: Company,
    session: Session = get_session(),
) -> Optional[Company]:
    """Create a new company and add it to the database."""
    new_company = Company(
        vat_number=company.vat_number,
        name=company.name,
        email=company.email,
        summary_activities=company.summary_activities,
        accreditations=company.accreditations,
        interested_cpv_codes=company.interested_cpv_codes,
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
    vat_number: str, session: Session = get_session()
) -> Optional[Company]:
    """Retrieve a company by its VAT number."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_cpv_codes).joinedload(
                    CPVCode.descriptions
                ),
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


def get_all_companies(
    limit: int = 100, session: Session = get_session()
) -> List[Company]:
    """Retrieve all companies with optional pagination."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_cpv_codes).joinedload(
                    CPVCode.descriptions
                ),
                joinedload(Company.recommended_publications),
            )
            .limit(limit)
            .all()
        )
    except Exception as e:
        logging.error("Error getting all companies: %s", e)
        return None
    finally:
        session.close()


def update_company(
    vat_number: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    summary_activities: Optional[str] = None,
    interested_cpv_codes: Optional[List[CPVCode]] = None,
    session: Session = get_session(),
) -> Optional[Company]:
    """Update the details of an existing company."""
    company = session.query(Company).filter(Company.vat_number == vat_number).first()
    if not company:
        logging.error(
            "Company with VAT number %s not found. Update failed.", vat_number
        )
        return False

    if name:
        company.name = name
    if email:
        company.email = email
    if summary_activities:
        company.summary_activities = summary_activities
    if interested_cpv_codes is not None:
        company.interested_cpv_codes = interested_cpv_codes

    try:
        session.commit()
        return company
    except Exception as e:
        session.rollback()
        logging.error("Error updating company: %s", e)
        return None


def delete_company(vat_number: str, session: Session = get_session()) -> bool:
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
    email: str, session: Session = get_session()
) -> Optional[Company]:
    """Retrieve a company by its email."""
    try:
        return (
            session.query(Company)
            .options(
                joinedload(Company.interested_cpv_codes).joinedload(
                    CPVCode.descriptions
                ),
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
