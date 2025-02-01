from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.postgres import get_session
from models.publication_models import Company, CPVCode, Publication


def create_company(
    vat_number: str,
    name: str,
    email: str,
    summary_activities: str,
    interested_cpv_codes: Optional[List[CPVCode]] = None,
    session: Session = get_session(),
) -> Optional[Company]:
    """Create a new company and add it to the database."""
    new_company = Company(
        vat_number=vat_number,
        name=name,
        email=email,
        summary_activities=summary_activities,
        interested_cpv_codes=interested_cpv_codes if interested_cpv_codes else [],
    )
    try:
        session.add(new_company)
        session.commit()
        return new_company
    except IntegrityError:
        session.rollback()
        print(f"A company with VAT number {vat_number} already exists.")
        return None


def get_company_by_vat_number(
    vat_number: str, session: Session = get_session()
) -> Optional[Company]:
    """Retrieve a company by its VAT number."""
    return session.query(Company).filter(Company.vat_number == vat_number).first()


def get_all_companies(
    skip: int = 0, limit: int = 100, session: Session = get_session()
) -> List[Company]:
    """Retrieve all companies with optional pagination."""
    return session.query(Company).offset(skip).limit(limit).all()


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
        print(f"Company with VAT number {vat_number} not found.")
        return None

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
    except IntegrityError:
        session.rollback()
        print("Error updating the company.")
        return None


def delete_company(vat_number: str, session: Session = get_session()) -> bool:
    """Delete a company by its VAT number."""
    company = session.query(Company).filter(Company.vat_number == vat_number).first()
    if not company:
        print(f"Company with VAT number {vat_number} not found.")
        return False

    session.delete(company)
    session.commit()
    return True


def get_recommended_publications(
    vat_number: str, session: Session = get_session()
) -> Optional[List[Publication]]:
    return (
        session.query(Company)
        .filter(Company.vat_number == vat_number)
        .first()
        .recommended_publications
    )
