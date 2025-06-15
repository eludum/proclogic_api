import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from fastapi_pagination import Page, Params

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.config.postgres import get_session
from app.config.settings import Settings
from app.crud.publication_mapper import (
    convert_publication_to_out_schema_details_free,
    convert_publication_to_out_schema_details_paid,
    convert_publications_to_out_schema_list_free,
    convert_publications_to_out_schema_list_paid,
)
from app.crud.publication_related import get_related_awarded_contracts
from app.crud.publication_semantic import (
    get_paginated_publications_with_semantic_search,
)
from app.schemas.publication_out_schemas import PublicationOut
from app.schemas.publication_related_schemas import (
    RelatedContentResponse,
    RelatedContractItem,
)
from app.util.clerk import AuthUser, get_auth_user
from app.util.kanban_integration import remove_unsaved_publication_from_kanban
from app.util.publication_utils.cpv_codes import get_cpv_sector_name
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.publication_utils.semantic_search import semantic_search
from app.util.pubproc import get_publication_workspace_documents

settings = Settings()
publications_router = APIRouter()
security = HTTPBearer()


# Update the existing get_publications endpoint to use semantic search
@publications_router.get("/publications/", response_model=Page[PublicationOut])
async def get_publications(
    recommended: bool = Query(None, description="Filter by recommended publications"),
    saved: bool = Query(None, description="Filter by saved publications"),
    viewed: bool = Query(None, description="Filter by viewed publications"),
    active: bool = Query(True, description="Filter by active publications only"),
    search_term: str = Query(
        None, description="Search in title, description, or organization"
    ),
    use_semantic_search: bool = Query(
        True,
        description="Use AI-powered semantic search (when search_term is provided)",
    ),
    similarity_threshold: float = Query(
        0.5,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for semantic search (0-1)",
    ),
    region: List[str] = Query(None, description="Filter by region codes"),
    sector: List[str] = Query(None, description="Filter by sector"),
    cpv_code: List[str] = Query(None, description="Filter by CPV codes"),
    date_from: Optional[datetime.date] = Query(
        None, description="Filter publications from this date"
    ),
    date_to: Optional[datetime.date] = Query(
        None, description="Filter publications until this date"
    ),
    sort_by: str = Query(
        None,
        description="Sort field: match_percentage, publication_date, deadline, relevance",
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    auth_user: AuthUser = Depends(get_auth_user),
) -> Page[PublicationOut]:
    """
    Get publications with flexible filtering options.

    When a search_term is provided and use_semantic_search is True (default),
    the system uses AI embeddings to understand the meaning of your search
    and find relevant publications even if they don't contain the exact keywords.

    The semantic search:
    - Understands context and synonyms
    - Finds related concepts
    - Ranks results by relevance
    - Combines with traditional keyword matching for best results

    Sorting is applied automatically based on active filters:
    - When using semantic search: Sort by relevance score
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

        # Use the enhanced semantic search function
        publications, total = await get_paginated_publications_with_semantic_search(
            session=session,
            company_vat_number=company.vat_number,
            page=page,
            size=size,
            search_term=search_term,
            use_semantic_search=use_semantic_search,
            similarity_threshold=similarity_threshold,
            recommended=recommended,
            saved=saved,
            viewed=viewed,
            active=active,
            region_filter=region,
            sector_filter=sector,
            cpv_code_filter=cpv_code,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Convert to output schema
        items = []
        for publication in publications:
            output = await convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            items.append(output)

        # Create a Page response with the correct total
        params = Params(page=page, size=size)
        return Page.create(items=items, total=total, params=params)


@publications_router.get(
    "/publications/publication/{publication_workspace_id}/explain-match",
)
async def explain_search_match(
    publication_workspace_id: str = Path(
        ..., description="Unique ID of the publication workspace"
    ),
    search_query: str = Query(..., description="The search query to explain"),
    auth_user: AuthUser = Depends(get_auth_user),
) -> dict:
    """
    Explain why a publication matched a specific search query.

    Returns the most relevant text chunk that caused the match.
    """
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get the explanation
        matching_chunk = await semantic_search.explain_match(
            session=session,
            publication_workspace_id=publication_workspace_id,
            query=search_query,
        )

        if not matching_chunk:
            raise HTTPException(
                status_code=404, detail="Could not find matching content for this query"
            )

        return {
            "publication_workspace_id": publication_workspace_id,
            "search_query": search_query,
            "matching_content": matching_chunk,
            "explanation": f"This publication matched your search because it contains content similar to '{search_query}'",
        }


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
async def mark_publication_viewed(
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
    auth_user: Optional[AuthUser] = Depends(get_auth_user),
) -> RelatedContentResponse:
    """
    Get related contracts and active publications for a specific publication.

    This endpoint finds:
    - Related awarded contracts based on CPV codes, organization, region, and keywords
    - Related active publications that are similar to the selected publication

    Similarity is calculated based on:
    - CPV code matching (highest priority)
    - Same contracting authority
    - Geographic overlap (NUTS codes)
    - Keyword similarity
    - Value range similarity
    """
    with get_session() as session:
        # Get the source publication
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        # Get user's company if authenticated
        company = None
        if auth_user and auth_user.email:
            company = crud_company.get_company_by_email(
                email=auth_user.email, session=session
            )

        # Get related contracts
        related_contracts_data = get_related_awarded_contracts(
            publication=publication, session=session, limit=contracts_limit
        )

        # Convert to response format
        related_contracts = []
        for pub, score, reason in related_contracts_data:
            if pub.contract:
                contract_value = 0
                winner = "Unknown"
                award_date = None

                # Extract contract details based on your contract model
                if (
                    hasattr(pub.contract, "total_contract_amount")
                    and pub.contract.total_contract_amount
                ):
                    contract_value = pub.contract.total_contract_amount

                if (
                    hasattr(pub.contract, "winning_publisher")
                    and pub.contract.winning_publisher
                ):
                    winner = pub.contract.winning_publisher.name

                if hasattr(pub.contract, "issue_date") and pub.contract.issue_date:
                    award_date = datetime.combine(
                        pub.contract.issue_date, datetime.min.time()
                    )
                else:
                    award_date = pub.publication_date

                related_contracts.append(
                    RelatedContractItem(
                        publication_id=pub.publication_workspace_id,
                        title=PublicationConverter.get_descr_as_str(pub.dossier.titles),
                        award_date=award_date,
                        winner=winner,
                        value=contract_value,
                        sector=get_cpv_sector_name(pub.cpv_main_code.code, "nl"),
                        cpv_code=pub.cpv_main_code.code,
                        buyer=PublicationConverter.get_org_name_as_str(
                            pub.organisation.organisation_names
                        ),
                        similarity_score=score,
                        similarity_reason=reason,
                    )
                )

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

    # Get the file object - it will always be a BytesIO object now
    file_data = documents[filename]

    # Reset position to start of file
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

    # Return the file directly as a streaming response
    return StreamingResponse(
        file_data,  # We can pass the BytesIO object directly
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
