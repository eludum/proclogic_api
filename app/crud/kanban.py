import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import asc, func
from sqlalchemy.orm import Session, aliased, joinedload

from app.models.company_models import Company
from app.models.kanban_models import KanbanStatus, PublicationStatus
from app.models.publication_models import Publication
from app.schemas.publication_out_schemas import PublicationOut
from app.util.publication_utils.publication_converter import PublicationConverter


# KanbanStatus CRUD operations
def create_kanban_status(
    company_vat_number: str, name: str, color: str, position: int, is_default: bool, session: Session
) -> Optional[KanbanStatus]:
    """Create a new Kanban status for a company."""
    try:
        # Check if company exists
        company = session.query(Company).filter(Company.vat_number == company_vat_number).first()
        if not company:
            logging.error(f"Company with VAT number {company_vat_number} not found")
            return None

        # Create the new status
        status = KanbanStatus(
            name=name,
            color=color,
            position=position,
            is_default=is_default,
            company_vat_number=company_vat_number
        )
        
        session.add(status)
        session.commit()
        session.refresh(status)
        return status
    except Exception as e:
        logging.error(f"Error creating Kanban status: {e}")
        session.rollback()
        return None


def get_kanban_statuses(company_vat_number: str, session: Session) -> List[KanbanStatus]:
    """Get all Kanban statuses for a company, ordered by position."""
    try:
        return session.query(KanbanStatus).filter(
            KanbanStatus.company_vat_number == company_vat_number
        ).order_by(KanbanStatus.position).all()
    except Exception as e:
        logging.error(f"Error getting Kanban statuses: {e}")
        return []


def get_kanban_status(status_id: int, company_vat_number: str, session: Session) -> Optional[KanbanStatus]:
    """Get a specific Kanban status."""
    try:
        return session.query(KanbanStatus).filter(
            KanbanStatus.id == status_id,
            KanbanStatus.company_vat_number == company_vat_number
        ).first()
    except Exception as e:
        logging.error(f"Error getting Kanban status: {e}")
        return None


def update_kanban_status(
    status_id: int, company_vat_number: str, updates: Dict, session: Session
) -> Optional[KanbanStatus]:
    """Update a Kanban status."""
    try:
        status = get_kanban_status(status_id, company_vat_number, session)
        if not status:
            return None

        # Update fields
        for key, value in updates.items():
            if hasattr(status, key) and value is not None:
                setattr(status, key, value)

        session.commit()
        session.refresh(status)

        return status
    except Exception as e:
        logging.error(f"Error updating Kanban status: {e}")
        session.rollback()
        return None


def delete_kanban_status(status_id: int, company_vat_number: str, session: Session) -> bool:
    """Delete a Kanban status."""
    try:
        status = get_kanban_status(status_id, company_vat_number, session)
        if not status:
            return False

        # Check if this is the only status left
        count = session.query(func.count(KanbanStatus.id)).filter(
            KanbanStatus.company_vat_number == company_vat_number
        ).scalar()
        
        if count <= 1:
            logging.error("Cannot delete the only Kanban status")
            return False
        
        # Find an alternative status for publications in this status
        alternative_status = session.query(KanbanStatus).filter(
            KanbanStatus.company_vat_number == company_vat_number,
            KanbanStatus.id != status_id
        ).first()
        
        # Move all publications in this status to the alternative status
        if alternative_status:
            session.query(PublicationStatus).filter(
                PublicationStatus.status_id == status_id
            ).update({
                "status_id": alternative_status.id
            })
        
        # Now delete the status
        session.delete(status)
        session.commit()
        session.refresh(status)
        return True
    except Exception as e:
        logging.error(f"Error deleting Kanban status: {e}")
        session.rollback()
        return False


# PublicationStatus CRUD operations
def set_publication_status(
    company_vat_number: str, 
    publication_workspace_id: str, 
    status_id: int, 
    notes: Optional[str] = None,
    position: int = 0,
    session: Session = None
) -> Optional[PublicationStatus]:
    """Set or update the status of a publication for a company."""
    try:
        # Check if publication and status exist
        publication = session.query(Publication).filter(
            Publication.publication_workspace_id == publication_workspace_id
        ).first()
        
        status = session.query(KanbanStatus).filter(
            KanbanStatus.id == status_id,
            KanbanStatus.company_vat_number == company_vat_number
        ).first()
        
        if not publication or not status:
            return None
        
        # Check if a status already exists for this publication
        pub_status = session.query(PublicationStatus).filter(
            PublicationStatus.company_vat_number == company_vat_number,
            PublicationStatus.publication_workspace_id == publication_workspace_id
        ).first()
        
        if pub_status:
            # Update existing status
            pub_status.status_id = status_id
            if notes is not None:
                pub_status.notes = notes
            pub_status.position = position
        else:
            # Create new status
            pub_status = PublicationStatus(
                company_vat_number=company_vat_number,
                publication_workspace_id=publication_workspace_id,
                status_id=status_id,
                notes=notes,
                position=position
            )
            session.add(pub_status)
        
        session.commit()
        session.refresh(status)

        return pub_status
    except Exception as e:
        logging.error(f"Error setting publication status: {e}")
        session.rollback()
        return None


def get_publication_status(
    company_vat_number: str, 
    publication_workspace_id: str, 
    session: Session
) -> Optional[PublicationStatus]:
    """Get the status of a publication for a company."""
    try:
        return session.query(PublicationStatus).filter(
            PublicationStatus.company_vat_number == company_vat_number,
            PublicationStatus.publication_workspace_id == publication_workspace_id
        ).options(
            joinedload(PublicationStatus.status)
        ).first()
    except Exception as e:
        logging.error(f"Error getting publication status: {e}")
        return None


def update_publication_status(
    company_vat_number: str,
    publication_workspace_id: str,
    updates: Dict,
    session: Session
) -> Optional[PublicationStatus]:
    """Update the status details of a publication."""
    try:
        pub_status = get_publication_status(company_vat_number, publication_workspace_id, session)
        if not pub_status:
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(pub_status, key) and value is not None:
                setattr(pub_status, key, value)
        
        session.commit()
        session.refresh(pub_status)
        return pub_status
    except Exception as e:
        logging.error(f"Error updating publication status: {e}")
        session.rollback()
        return None


def remove_publication_status(
    company_vat_number: str,
    publication_workspace_id: str,
    session: Session
) -> bool:
    """Remove a publication from the Kanban board."""
    try:
        pub_status = session.query(PublicationStatus).filter(
            PublicationStatus.company_vat_number == company_vat_number,
            PublicationStatus.publication_workspace_id == publication_workspace_id
        ).first()
        
        if not pub_status:
            return False
        
        session.delete(pub_status)
        session.commit()
        session.refresh(pub_status)
        return True
    except Exception as e:
        logging.error(f"Error removing publication status: {e}")
        session.rollback()
        return False


def move_publication(
    company_vat_number: str,
    publication_workspace_id: str,
    new_status_id: int,
    new_position: int,
    session: Session
) -> Optional[PublicationStatus]:
    """Move a publication to a different status and/or position."""
    try:
        # Verify the new status exists
        status = session.query(KanbanStatus).filter(
            KanbanStatus.id == new_status_id,
            KanbanStatus.company_vat_number == company_vat_number
        ).first()
        
        if not status:
            return None
        
        # Get the current publication status
        pub_status = get_publication_status(company_vat_number, publication_workspace_id, session)
        if not pub_status:
            return None
        
        # Update the status and position
        pub_status.status_id = new_status_id
        pub_status.position = new_position
        
        session.commit()
        
        session.refresh(pub_status)
        
        return pub_status
    except Exception as e:
        logging.error(f"Error moving publication: {e}")
        session.rollback()
        return None

def get_kanban_board(company_vat_number: str, session: Session) -> Tuple[List[dict], List[dict]]:
    """
    Get the full Kanban board view with all statuses and their publications.
    Returns a tuple of (statuses, publications_by_status_id)
    """
    try:
        # Get all statuses
        statuses = session.query(KanbanStatus).filter(
            KanbanStatus.company_vat_number == company_vat_number
        ).order_by(KanbanStatus.position).all()
        
        # Get all publications with their statuses
        pub_statuses = session.query(
            PublicationStatus,
            Publication
        ).join(
            Publication,
            PublicationStatus.publication_workspace_id == Publication.publication_workspace_id
        ).filter(
            PublicationStatus.company_vat_number == company_vat_number
        ).all()
        
        # Group publications by status_id
        publications_by_status = {}
        for status in statuses:
            publications_by_status[status.id] = []
        
        for pub_status, publication in pub_statuses:
            # Create a simplified publication object with essential information
            publication_data = {
                "publication_workspace_id": publication.publication_workspace_id,
                "title": PublicationConverter.get_descr_as_str(publication.dossier.titles),
                "organisation": PublicationConverter.get_descr_as_str(publication.organisation.organisation_names),
                "submission_deadline": publication.vault_submission_deadline,
                "is_active": publication.is_active,
                "notes": pub_status.notes,
                "position": pub_status.position,
            }
            
            # Find match percentage if available
            for match in publication.company_matches:
                if match.company_vat_number == company_vat_number:
                    publication_data["match_percentage"] = match.match_percentage
                    break
            
            # Add to the appropriate status
            if pub_status.status_id in publications_by_status:
                publications_by_status[pub_status.status_id].append(publication_data)
        
        # Sort publications by position within each status
        for status_id in publications_by_status:
            publications_by_status[status_id].sort(key=lambda p: p["position"])
        
        return statuses, publications_by_status
    except Exception as e:
        logging.error(f"Error getting Kanban board: {e}")
        return [], {}


def initialize_default_kanban_statuses(company_vat_number: str, session: Session) -> bool:
    """Initialize default Kanban statuses for a new company."""
    try:
        # Check if company already has statuses
        existing_statuses = session.query(KanbanStatus).filter(
            KanbanStatus.company_vat_number == company_vat_number
        ).count()
        
        if existing_statuses > 0:
            # Company already has statuses
            return True
        
        # Create default statuses
        default_statuses = [
            {"name": "Opgeslagen", "color": "#3883a4", "position": 0, "is_default": True},
            {"name": "In voorbereiding", "color": "#52b7c2", "position": 1, "is_default": False},
            {"name": "Ingediend", "color": "#b7bf10", "position": 2, "is_default": False},
        ]
        
        for status_data in default_statuses:
            status = KanbanStatus(
                name=status_data["name"],
                color=status_data["color"],
                position=status_data["position"],
                is_default=status_data["is_default"],
                company_vat_number=company_vat_number
            )
            session.add(status)
        
        session.commit()
        session.refresh(status)
        return True
    except Exception as e:
        logging.error(f"Error initializing default Kanban statuses: {e}")
        session.rollback()
        return False