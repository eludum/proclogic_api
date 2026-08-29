from datetime import date
from typing import List, Optional
from urllib.parse import quote

import app.crud.company as crud_company
import app.crud.publication as crud_publication
import httpx
from app.config.postgres import get_session
from app.crud.publication_mapper import (
    convert_publication_to_out_schema_details_free,
    convert_publication_to_out_schema_details_paid,
    convert_publications_to_out_schema_list_free,
    convert_publications_to_out_schema_list_paid,
)
from app.ai.retrieval_agent import find_similar_awards
from app.mcp.context import build_context_async
from app.schemas.publication_out_schemas import PublicationOut
from app.schemas.publication_related_schemas import (
    RelatedContentResponse,
    RelatedContractItem,
)
from app.util.clerk import AuthUser, get_auth_user
from app.util.kanban_integration import remove_unsaved_publication_from_kanban
from app.util.pubproc import get_publication_workspace_documents
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from fastapi_pagination import Page, Params


publications_router = APIRouter()
security = HTTPBearer()


@publications_router.get("/publications/", response_model=Page[PublicationOut])
async def get_publications(
    recommended: bool = Query(None, description="Filter by recommended publications"),
    saved: bool = Query(None, description="Filter by saved publications"),
    viewed: bool = Query(None, description="Filter by viewed publications"),
    active: bool = Query(True, description="Filter by active publications only"),
    search_term: str = Query(
        None, description="Search in title, description, or organization"
    ),
    region: List[str] = Query(None, description="Filter by region codes"),
    sector: List[str] = Query(None, description="Filter by sector"),
    cpv_code: List[str] = Query(None, description="Filter by CPV codes"),
    date_from: Optional[date] = Query(
        None, description="Filter publications from this date"
    ),
    date_to: Optional[date] = Query(
        None, description="Filter publications until this date"
    ),
    sort_by: str = Query(
        None, description="Sort field: match_percentage, publication_date, deadline"
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    auth_user: AuthUser = Depends(get_auth_user),
) -> Page[PublicationOut]:
    """
    Get publications with flexible filtering options.
    Returns paginated publications that match all provided filters.

    Sorting is applied automatically based on active filters:
    - When recommended=True: Sort by match_percentage (desc) then publication_date (desc)
    - When saved=True: Sort by when the publication was saved (desc)
    - When view=True: Sort by when the publication was viewed (desc)
    - Default: Sort by publication_date (desc)

    Custom sorting can override these defaults using sort_by and sort_order parameters.
    """
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publications, total = crud_publication.get_paginated_publications_for_company(
            session=session,
            company_vat_number=company.vat_number,
            page=page,
            size=size,
            recommended=recommended,
            saved=saved,
            viewed=viewed,
            active=active,
            search_term=search_term,
            region_filter=region,
            sector_filter=sector,
            cpv_code_filter=cpv_code,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Convert to output schema
        items = [
            await convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ]

        # Create a Page response with the correct total
        params = Params(page=page, size=size)
        return Page.create(items=items, total=total, params=params)


@publications_router.get(
    "/publications/free/search/",
    response_model=Page[PublicationOut],
)
async def search_publications_free(
    search_term: Optional[str] = Query(None, description="Search term"),
    region: List[str] = Query(None, description="Filter by region codes"),
    sector: List[str] = Query(None, description="Filter by sector"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("publication_date", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
) -> Page[PublicationOut]:
    """
    Search publications without authentication (free version).
    Uses optimized database queries with pagination and sorting.
    """
    with get_session() as session:
        publications, total = crud_publication.get_paginated_publications_free(
            session=session,
            page=page,
            size=size,
            search_term=search_term,
            sort_by=sort_by,
            sort_order=sort_order,
            region_filter=region,
            sector_filter=sector,
        )

        # Convert publications to output schema
        items = [
            await convert_publications_to_out_schema_list_free(publication=pub)
            for pub in publications
        ]

        # Create a Page response with the correct total
        params = Params(page=page, size=size)
        return Page.create(items=items, total=total, params=params)


@publications_router.get(
    "/publications/publication/{publication_workspace_id}/",
    response_model=PublicationOut,
)
async def get_publication_by_workspace_id(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
) -> PublicationOut:
    """Get a specific publication by workspace ID"""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        # Mark as viewed
        crud_company.mark_publication_as_viewed(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        return await convert_publication_to_out_schema_details_paid(
            publication=publication, company=company
        )


@publications_router.get(
    "/publications/free/publication/{publication_workspace_id}/",
    response_model=PublicationOut,
)
async def get_publication_free(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
) -> PublicationOut:
    """Get a specific publication by workspace ID without authentication (free tier)"""
    with get_session() as session:
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        return await convert_publication_to_out_schema_details_free(
            publication=publication
        )


@publications_router.post(
    "/publications/publication/{publication_workspace_id}/save",
    status_code=200,
)
async def save_publication(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Save a publication for the authenticated user's company and add it to Kanban board."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )
        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        # Save the publication
        success = crud_company.save_publication_for_company(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save publication")

        # Add to Kanban board
        from app.util.kanban_integration import add_saved_publication_to_kanban

        await add_saved_publication_to_kanban(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        return {"message": "Publication saved successfully"}


@publications_router.post(
    "/publications/publication/{publication_workspace_id}/unsave",
    status_code=200,
)
async def unsave_publication(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Remove a publication from saved list and from the Kanban board."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )
        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        # Unsave the publication
        success = crud_company.unsave_publication_for_company(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Publication was not saved")

        # Remove from Kanban board
        await remove_unsaved_publication_from_kanban(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        return {"message": "Publication removed from saved list"}


@publications_router.post(
    "/publications/publication/{publication_workspace_id}/viewed",
    status_code=200,
)
def mark_publication_viewed(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Mark a publication as viewed by the authenticated user's company"""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )
        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        success = crud_company.mark_publication_as_viewed(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to mark publication as viewed"
            )

        return {"message": "Publication marked as viewed"}


@publications_router.get(
    "/publications/publication/{publication_workspace_id}/related",
    response_model=RelatedContentResponse,
)
async def get_related_content(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
    contracts_limit: int = Query(
        10, ge=1, le=20, description="Number of related contracts to return"
    ),
    refresh: bool = Query(
        False, description="Bypass the cache and re-run the search"
    ),
    auth_user: Optional[AuthUser] = Depends(get_auth_user),
) -> RelatedContentResponse:
    """
    Get awarded contracts comparable to this publication.

    The results are found by searching the award database, not inferred from
    metadata: a retrieval agent queries the contracts with its own search terms,
    ranks what it finds, and explains each match. Every item returned is a real
    award row -- ``similarity_score`` and ``similarity_reason`` are the only
    fields the model contributes, and the score is a genuine 0-100 relevance
    rather than the open-ended point total this endpoint used to return.

    Results are cached per publication; pass ``refresh=true`` to recompute. If
    the agent is unavailable or times out, this falls back to the deterministic
    scorer so the section still renders.
    """
    with get_session() as session:
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

    ctx = None
    if auth_user:
        ctx = await build_context_async(auth_user.user_id, auth_user.email)

    similar = await find_similar_awards(
        workspace_id=publication_workspace_id,
        limit=contracts_limit,
        ctx=ctx,
        use_cache=not refresh,
    )

    related_contracts = [
        RelatedContractItem(
            publication_id=item["workspace_id"],
            title=item.get("title") or "Untitled",
            award_date=item.get("award_date"),
            winner=item.get("winner") or "Unknown",
            value=item.get("value") or 0.0,
            sector=item.get("sector") or "N/A",
            cpv_code=item.get("cpv_code") or "",
            buyer=item.get("buyer") or "Unknown",
            similarity_score=item.get("similarity_score") or 0.0,
            similarity_reason=item.get("similarity_reason") or "",
        )
        for item in similar
    ]

    return RelatedContentResponse(
        related_contracts=related_contracts,
        total_contracts=len(related_contracts),
    )


@publications_router.get(
    "/publications/publication/{publication_workspace_id}/document/{filename}",
)
async def get_publication_document(
    publication_workspace_id: str,
    filename: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get a specific document from a publication."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Check if publication exists
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )
        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

    # Get the document
    async with httpx.AsyncClient() as client:
        documents = await get_publication_workspace_documents(
            client=client, publication_workspace_id=publication_workspace_id
        )

    if not documents or filename not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    # The cache decorator always returns {filename: BytesIO}, fresh or cached.
    file_data = documents[filename]
    file_data.seek(0)

    # Determine content type
    content_type = "application/octet-stream"  # Default
    if filename.lower().endswith(".pdf"):
        content_type = "application/pdf"
    elif filename.lower().endswith((".doc", ".docx")):
        content_type = "application/msword"
    elif filename.lower().endswith((".xls", ".xlsx")):
        content_type = "application/vnd.ms-excel"
    elif filename.lower().endswith(".txt"):
        content_type = "text/plain"
    elif filename.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif filename.lower().endswith(".png"):
        content_type = "image/png"

    # filename comes from the upstream notice, not from us. A quote or a newline
    # in it would corrupt the header, so quote it properly and send the RFC 5987
    # form alongside for anything non-ASCII.
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    safe_name = ascii_name.replace("\\", "_").replace('"', "_").replace("\r", "").replace("\n", "")
    disposition = (
        f'attachment; filename="{safe_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )

    # Return the file directly as a streaming response
    return StreamingResponse(
        file_data,  # We can pass the BytesIO object directly
        media_type=content_type,
        headers={"Content-Disposition": disposition},
    )
