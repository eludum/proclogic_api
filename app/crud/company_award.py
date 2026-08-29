"""Reads and writes for company-supplied award data.

Every function here takes ``company_vat_number`` and filters on it. That is the
isolation boundary, and it is a parameter rather than something derived inside
so there is no code path that can read or write an entry without naming whose it
is. The router resolves it from the authenticated caller's email; it is never
taken from a request body or query string.
"""

import logging
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.company_award_models import (
    OVERRIDABLE_FIELDS,
    SOURCE_MANUAL,
    CompanyAwardEntry,
)

logger = logging.getLogger(__name__)


def get_entry(
    session: Session, company_vat_number: str, publication_workspace_id: str
) -> Optional[CompanyAwardEntry]:
    """This company's overlay for one BOSA award, if it has one."""
    return (
        session.query(CompanyAwardEntry)
        .filter(
            CompanyAwardEntry.company_vat_number == company_vat_number,
            CompanyAwardEntry.publication_workspace_id == publication_workspace_id,
        )
        .first()
    )


def get_entries_for_publications(
    session: Session, company_vat_number: str, publication_ids: Sequence[str]
) -> Dict[str, CompanyAwardEntry]:
    """Overlays for a page of awards, keyed by publication id.

    One query for the whole page: the awards list renders up to 500 rows, and
    asking per row would be 500 round trips.
    """
    if not publication_ids:
        return {}

    rows = (
        session.query(CompanyAwardEntry)
        .filter(
            CompanyAwardEntry.company_vat_number == company_vat_number,
            CompanyAwardEntry.publication_workspace_id.in_(list(publication_ids)),
        )
        .all()
    )
    return {r.publication_workspace_id: r for r in rows}


def upsert_entry(
    session: Session,
    company_vat_number: str,
    created_by_email: str,
    publication_workspace_id: Optional[str],
    fields: dict,
    source: str = SOURCE_MANUAL,
    source_document_name: Optional[str] = None,
) -> CompanyAwardEntry:
    """Create or update this company's entry.

    Only keys present in ``fields`` are touched, so a partial save (the user
    filled in one missing amount) does not blank everything else. A key present
    with a None value clears that field, which is how a company reverts one
    field to the BOSA value without deleting the whole entry.
    """
    entry = None
    if publication_workspace_id is not None:
        entry = get_entry(session, company_vat_number, publication_workspace_id)

    if entry is None:
        entry = CompanyAwardEntry(
            company_vat_number=company_vat_number,
            created_by_email=created_by_email,
            publication_workspace_id=publication_workspace_id,
            source=source,
            source_document_name=source_document_name,
        )
        session.add(entry)
    else:
        entry.source = source
        if source_document_name is not None:
            entry.source_document_name = source_document_name

    for field in OVERRIDABLE_FIELDS:
        if field in fields:
            setattr(entry, field, fields[field])

    session.commit()
    session.refresh(entry)
    return entry


def delete_entry(
    session: Session, company_vat_number: str, publication_workspace_id: str
) -> bool:
    """Drop the overlay, restoring the plain BOSA view. True if one existed."""
    entry = get_entry(session, company_vat_number, publication_workspace_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def list_company_awards(
    session: Session, company_vat_number: str
) -> List[CompanyAwardEntry]:
    """Awards this company entered itself (no BOSA row behind them)."""
    return (
        session.query(CompanyAwardEntry)
        .filter(
            CompanyAwardEntry.company_vat_number == company_vat_number,
            CompanyAwardEntry.publication_workspace_id.is_(None),
        )
        .order_by(CompanyAwardEntry.created_at.desc())
        .all()
    )


def get_by_id(
    session: Session, company_vat_number: str, entry_id: int
) -> Optional[CompanyAwardEntry]:
    """One entry by id, scoped to the company so an id from elsewhere misses."""
    return (
        session.query(CompanyAwardEntry)
        .filter(
            CompanyAwardEntry.id == entry_id,
            CompanyAwardEntry.company_vat_number == company_vat_number,
        )
        .first()
    )


def update_by_id(
    session: Session, company_vat_number: str, entry_id: int, fields: dict
) -> Optional[CompanyAwardEntry]:
    entry = get_by_id(session, company_vat_number, entry_id)
    if entry is None:
        return None

    for field in OVERRIDABLE_FIELDS:
        if field in fields:
            setattr(entry, field, fields[field])

    session.commit()
    session.refresh(entry)
    return entry


def delete_by_id(session: Session, company_vat_number: str, entry_id: int) -> bool:
    entry = get_by_id(session, company_vat_number, entry_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def merge_over(item, entry: Optional[CompanyAwardEntry]):
    """Apply a company's supplied values on top of a BOSA award item.

    Returns the field names that came from the company, so the caller can mark
    them in the UI. Mutates ``item`` in place -- it is a per-request pydantic
    object, not anything shared.
    """
    if entry is None:
        return []

    supplied = entry.supplied()
    for field, value in supplied.items():
        if hasattr(item, field):
            setattr(item, field, value)
    return sorted(supplied.keys())
