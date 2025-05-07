from typing import List

from fastapi import APIRouter, Depends, HTTPException

import app.crud.company as crud_company
import app.crud.kanban as crud_kanban
from app.config.postgres import get_session
from app.schemas.kanban_schemas import (
    KanbanBoard,
    KanbanColumn,
    KanbanStatusCreate,
    KanbanStatusResponse,
    KanbanStatusUpdate,
    MovePublicationRequest,
    PublicationInKanban,
    PublicationStatusCreate,
    PublicationStatusResponse,
    PublicationStatusUpdate,
)
from app.util.clerk import AuthUser, get_auth_user

kanban_router = APIRouter()


@kanban_router.get("/kanban/board", response_model=KanbanBoard)
async def get_kanban_board(auth_user: AuthUser = Depends(get_auth_user)):
    """Get the full Kanban board with all columns and publications."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Initialize default statuses if none exist
        crud_kanban.initialize_default_kanban_statuses(company.vat_number, session)

        # Get the board data
        statuses, publications_by_status = crud_kanban.get_kanban_board(
            company.vat_number, session
        )

        # Format as KanbanBoard response
        columns = []
        for status in statuses:
            publications = []
            for pub_data in publications_by_status.get(status.id, []):
                publications.append(PublicationInKanban(**pub_data))

            columns.append(
                KanbanColumn(
                    id=status.id,
                    name=status.name,
                    color=status.color,
                    position=status.position,
                    is_default=status.is_default,
                    publications=publications,
                )
            )

        return KanbanBoard(columns=columns)


@kanban_router.get("/kanban/statuses", response_model=List[KanbanStatusResponse])
async def get_kanban_statuses(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all Kanban statuses for the company."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Initialize default statuses if none exist
        crud_kanban.initialize_default_kanban_statuses(company.vat_number, session)

        statuses = crud_kanban.get_kanban_statuses(company.vat_number, session)
        return statuses


@kanban_router.post("/kanban/statuses", response_model=KanbanStatusResponse)
async def create_kanban_status(
    status: KanbanStatusCreate, auth_user: AuthUser = Depends(get_auth_user)
):
    """Create a new Kanban status."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        new_status = crud_kanban.create_kanban_status(
            company_vat_number=company.vat_number,
            name=status.name,
            color=status.color,
            position=status.position,
            is_default=status.is_default,
            session=session,
        )

        if not new_status:
            raise HTTPException(
                status_code=500, detail="Failed to create Kanban status"
            )

        return new_status


@kanban_router.put("/kanban/statuses/{status_id}", response_model=KanbanStatusResponse)
async def update_kanban_status(
    status_id: int,
    status_update: KanbanStatusUpdate,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Update a Kanban status."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Filter out None values from the update dict
        updates = {k: v for k, v in status_update.dict().items() if v is not None}

        updated_status = crud_kanban.update_kanban_status(
            status_id=status_id,
            company_vat_number=company.vat_number,
            updates=updates,
            session=session,
        )

        if not updated_status:
            raise HTTPException(status_code=404, detail="Kanban status not found")

        return updated_status


@kanban_router.delete("/kanban/statuses/{status_id}")
async def delete_kanban_status(
    status_id: int, auth_user: AuthUser = Depends(get_auth_user)
):
    """Delete a Kanban status and move its publications to another status."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        success = crud_kanban.delete_kanban_status(
            status_id=status_id, company_vat_number=company.vat_number, session=session
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to delete Kanban status. Make sure it's not the only status.",
            )

        return {"message": "Kanban status deleted successfully"}


@kanban_router.post("/kanban/publications", response_model=PublicationStatusResponse)
async def add_publication_to_kanban(
    publication_status: PublicationStatusCreate,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Add a publication to the Kanban board or update its status."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Initialize default statuses if none exist
        crud_kanban.initialize_default_kanban_statuses(company.vat_number, session)

        pub_status = crud_kanban.set_publication_status(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_status.publication_workspace_id,
            status_id=publication_status.status_id,
            notes=publication_status.notes,
            position=publication_status.position,
            session=session,
        )

        if not pub_status:
            raise HTTPException(
                status_code=404, detail="Publication or status not found"
            )

        return pub_status


@kanban_router.get(
    "/kanban/publications/{publication_workspace_id}",
    response_model=PublicationStatusResponse,
)
async def get_publication_kanban_status(
    publication_workspace_id: str, auth_user: AuthUser = Depends(get_auth_user)
):
    """Get the Kanban status of a specific publication."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        pub_status = crud_kanban.get_publication_status(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not pub_status:
            raise HTTPException(
                status_code=404, detail="Publication not found in Kanban board"
            )

        return pub_status


@kanban_router.put(
    "/kanban/publications/{publication_workspace_id}",
    response_model=PublicationStatusResponse,
)
async def update_publication_kanban_status(
    publication_workspace_id: str,
    status_update: PublicationStatusUpdate,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Update a publication's Kanban status details."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Filter out None values from the update dict
        updates = {k: v for k, v in status_update.dict().items() if v is not None}

        updated_status = crud_kanban.update_publication_status(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            updates=updates,
            session=session,
        )

        if not updated_status:
            raise HTTPException(
                status_code=404, detail="Publication not found in Kanban board"
            )

        return updated_status


@kanban_router.delete("/kanban/publications/{publication_workspace_id}")
async def remove_publication_from_kanban(
    publication_workspace_id: str, auth_user: AuthUser = Depends(get_auth_user)
):
    """Remove a publication from the Kanban board."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        success = crud_kanban.remove_publication_status(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not success:
            raise HTTPException(
                status_code=404, detail="Publication not found in Kanban board"
            )

        return {"message": "Publication removed from Kanban board"}


@kanban_router.post("/kanban/move", response_model=PublicationStatusResponse)
async def move_publication(
    move_request: MovePublicationRequest, auth_user: AuthUser = Depends(get_auth_user)
):
    """Move a publication to a different status and/or position."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        pub_status = crud_kanban.move_publication(
            company_vat_number=company.vat_number,
            publication_workspace_id=move_request.publication_workspace_id,
            new_status_id=move_request.new_status_id,
            new_position=move_request.new_position,
            session=session,
        )

        if not pub_status:
            raise HTTPException(
                status_code=404, detail="Publication or status not found"
            )

        return pub_status


@kanban_router.post("/kanban/initialize")
async def initialize_kanban_board(auth_user: AuthUser = Depends(get_auth_user)):
    """Initialize the Kanban board with default statuses."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        success = crud_kanban.initialize_default_kanban_statuses(
            company_vat_number=company.vat_number, session=session
        )

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to initialize Kanban board"
            )

        return {"message": "Kanban board initialized successfully"}
