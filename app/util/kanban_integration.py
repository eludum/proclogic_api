import logging
from sqlalchemy.orm import Session

import app.crud.company as crud_company
import app.crud.kanban as crud_kanban
import app.crud.publication as crud_publication


async def add_saved_publication_to_kanban(
    company_vat_number: str,
    publication_workspace_id: str,
    session: Session
) -> bool:
    """
    Helper function to automatically add a saved publication to the Kanban board.
    Called when a user saves a publication.
    """
    try:
        # Verify the publication exists
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id,
            session=session
        )
        
        if not publication:
            logging.error(f"Publication {publication_workspace_id} not found")
            return False
            
        # Initialize default statuses if they don't exist
        crud_kanban.initialize_default_kanban_statuses(company_vat_number, session)
        
        # Get the default status (typically "To Review")
        default_status = None
        statuses = crud_kanban.get_kanban_statuses(company_vat_number, session)
        
        for status in statuses:
            if status.is_default:
                default_status = status
                break
                
        if not default_status and statuses:
            # If no default status is marked, use the first one
            default_status = statuses[0]
            
        if not default_status:
            logging.error(f"No Kanban statuses found for company {company_vat_number}")
            return False
            
        # Check if the publication is already on the board
        existing_status = crud_kanban.get_publication_status(
            company_vat_number=company_vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session
        )
        
        if existing_status:
            # Publication is already on the board, no need to add it again
            return True
            
        # Count existing publications in the status to determine position
        pub_count = session.query(crud_kanban.PublicationStatus).filter(
            crud_kanban.PublicationStatus.company_vat_number == company_vat_number,
            crud_kanban.PublicationStatus.status_id == default_status.id
        ).count()
        
        # Add publication to the default status
        pub_status = crud_kanban.set_publication_status(
            company_vat_number=company_vat_number,
            publication_workspace_id=publication_workspace_id,
            status_id=default_status.id,
            position=pub_count,  # Add to the end of the column
            session=session
        )
        
        return pub_status is not None
    
    except Exception as e:
        logging.error(f"Error adding saved publication to Kanban: {e}")
        return False


async def remove_unsaved_publication_from_kanban(
    company_vat_number: str,
    publication_workspace_id: str,
    session: Session
) -> bool:
    """
    Helper function to remove a publication from the Kanban board when it's unsaved.
    Called when a user unsaves a publication.
    """
    try:
        # Check if the publication is on the board
        existing_status = crud_kanban.get_publication_status(
            company_vat_number=company_vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session
        )
        
        if not existing_status:
            # Publication is not on the board, nothing to do
            return True
            
        # Remove the publication from the board
        return crud_kanban.remove_publication_status(
            company_vat_number=company_vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session
        )
    
    except Exception as e:
        logging.error(f"Error removing unsaved publication from Kanban: {e}")
        return False


async def initialize_kanban_with_saved_publications(
    company_vat_number: str,
    session: Session
) -> bool:
    """
    Initialize a company's Kanban board with all their currently saved publications.
    Used when a company accesses the Kanban board for the first time.
    """
    try:
        # Initialize default statuses
        crud_kanban.initialize_default_kanban_statuses(company_vat_number, session)
        
        # Get all saved publications for this company
        saved_publications = crud_company.get_company_saved_publications(company_vat_number, session)
        
        if not saved_publications:
            # No saved publications, nothing to add
            return True
            
        # Get the default status
        default_status = None
        statuses = crud_kanban.get_kanban_statuses(company_vat_number, session)
        
        for status in statuses:
            if status.is_default:
                default_status = status
                break
                
        if not default_status and statuses:
            # If no default status is marked, use the first one
            default_status = statuses[0]
            
        if not default_status:
            logging.error(f"No Kanban statuses found for company {company_vat_number}")
            return False
            
        # Add each saved publication to the default status
        for i, publication in enumerate(saved_publications):
            # Skip publications that are already on the board
            existing_status = crud_kanban.get_publication_status(
                company_vat_number=company_vat_number,
                publication_workspace_id=publication.publication_workspace_id,
                session=session
            )
            
            if existing_status:
                continue
                
            # Add to the default status
            crud_kanban.set_publication_status(
                company_vat_number=company_vat_number,
                publication_workspace_id=publication.publication_workspace_id,
                status_id=default_status.id,
                position=i,  # Keep the order of the saved publications
                session=session
            )
        
        return True
    
    except Exception as e:
        logging.error(f"Error initializing Kanban with saved publications: {e}")
        return False