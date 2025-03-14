from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.security import HTTPBearer

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.config.postgres import get_session
from app.config.settings import Settings
from app.crud.mapper import (convert_publication_to_out_schema_details_free,
                             convert_publication_to_out_schema_details_paid,
                             convert_publications_to_out_schema_list_free,
                             convert_publications_to_out_schema_list_paid)
from app.schemas.publication_out_schemas import PublicationOut
from app.util.clerk import AuthUser, get_auth_user
from fastapi_pagination import Page, paginate

settings = Settings()
publications_router = APIRouter()
security = HTTPBearer()


@publications_router.get("/publications/", response_model=Page[PublicationOut])
async def get_publications(
    recommended: bool = Query(None, description="Filter by recommended publications"),
    saved: bool = Query(None, description="Filter by saved publications"),
    viewed: bool = Query(None, description="Filter by viewed publications"),
    active: bool = Query(True, description="Filter by active publications only"),
    search_term: str = Query(None, description="Search in title, description, or organization"),
    region: List[str] = Query(None, description="Filter by region codes"),
    sector: List[str] = Query(None, description="Filter by sector"),
    cpv_code: List[str] = Query(None, description="Filter by CPV codes"),
    date_from: Optional[date] = Query(None, description="Filter publications from this date"),
    date_to: Optional[date] = Query(None, description="Filter publications until this date"),
    sort_by: str = Query(None, description="Sort field: match_percentage, publication_date, deadline"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    auth_user: AuthUser = Depends(get_auth_user)
) -> List[PublicationOut]:
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

        # Get initial publications based on search term
        if not search_term or search_term.strip() == "":
            publications = crud_publication.get_all_publications(session=session)
        else:
            publications = crud_publication.search_publications(
                search_term=search_term, session=session
            )

        # Apply active filter
        if active:
            publications = [pub for pub in publications if pub.is_active]
        
        # Get specific matches for this company and enrich them with metadata
        matching_publications = []
        for publication in publications:
            # Find if there's a match record for this company
            match = None
            for pub_match in publication.company_matches:
                if pub_match.company_vat_number == company.vat_number:
                    match = pub_match
                    break
            
            # Skip publications that don't match our filters
            if recommended is not None and (not match or match.is_recommended != recommended):
                continue
                
            if saved is not None and (not match or match.is_saved != saved):
                continue
                
            if viewed is not None and (not match or match.is_viewed != viewed):
                continue
            
            # Enrich publication with sorting metadata
            if match:
                # Add metadata for sorting
                publication.match_percentage = match.match_percentage
                publication.saved_at = match.updated_at if match.is_saved else None
                publication.viewed_at = match.updated_at if match.is_viewed else None
            else:
                publication.match_percentage = 0
                publication.saved_at = None
                publication.viewed_at = None
            
            # If all filters passed, add to our results
            matching_publications.append(publication)
        
        # Replace with filtered list
        publications = matching_publications
            
        # Apply region filter if provided
        if region:
            publications = [
                pub for pub in publications 
                if any(reg in pub.nuts_codes for reg in region)
            ]
            
        # Apply sector filter if provided
        if sector:
            # Extract first two digits of CPV code for sector filtering
            publications = [
                pub for pub in publications
                if any(pub.cpv_main_code_code[:2] + "000000" == sec for sec in sector)
            ]
            
        # Apply CPV code filter if provided
        if cpv_code:
            filtered_publications = []
            for pub in publications:
                # Check if main CPV code matches
                if pub.cpv_main_code_code in cpv_code:
                    filtered_publications.append(pub)
                    continue
                    
                # Check if any additional CPV code matches
                if any(additional_cpv.code in cpv_code for additional_cpv in pub.cpv_additional_codes):
                    filtered_publications.append(pub)
                    continue
                    
            publications = filtered_publications
            
        # Apply date range filter if provided
        if date_from:
            publications = [
                pub for pub in publications if pub.publication_date.date() >= date_from
            ]
            
        if date_to:
            publications = [
                pub for pub in publications if pub.publication_date.date() <= date_to
            ]
        
        # Apply sorting based on active filters or explicit sort parameters
        if sort_by:
            # Explicit sorting takes precedence if provided
            reverse = sort_order.lower() == "desc"
            
            if sort_by == "match_percentage":
                publications.sort(key=lambda p: p.match_percentage, reverse=reverse)
            elif sort_by == "publication_date":
                publications.sort(key=lambda p: p.publication_date, reverse=reverse)
            elif sort_by == "deadline":
                # Sort by submission deadline, putting None values at the end
                publications.sort(
                    key=lambda p: (p.vault_submission_deadline is None, p.vault_submission_deadline), 
                    reverse=reverse
                )
        else:
            # Apply automatic sorting based on active filters
            if recommended:
                # For recommended publications, sort by match percentage (higher first), then by publication date
                publications.sort(
                    key=lambda p: (-p.match_percentage, -p.publication_date.timestamp() if p.publication_date else 0)
                )
            elif saved:
                # For saved publications, sort by saved date (newest first)
                publications.sort(
                    key=lambda p: (p.saved_at is None, -p.saved_at.timestamp() if p.saved_at else 0)
                )
            elif viewed:
                # For viewed publications, sort by viewed date (newest first)
                publications.sort(
                    key=lambda p: (p.viewed_at is None, -p.viewed_at.timestamp() if p.viewed_at else 0)
                )
            else:
                # Default sorting by publication date (newest first)
                publications.sort(
                    key=lambda p: (-p.publication_date.timestamp() if p.publication_date else 0)
                )

        # Convert to output schema and paginate
        return paginate([
            await convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ])


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
    "/publications/free/search/",
    response_model=Page[PublicationOut],
)
async def search_publications_free(
    search_term: Optional[str] = Query(None, description="Search term"),
    region: List[str] = Query(None, description="Filter by region codes"),
    sector: List[str] = Query(None, description="Filter by sector"),
) -> List[PublicationOut]:
    """Search publications without authentication (free version)"""
    with get_session() as session:
        # Get initial publications based on search term
        if not search_term or search_term.strip() == "":
            publications = crud_publication.get_all_publications(session=session)
        else:
            publications = crud_publication.search_publications(
                search_term=search_term, session=session
            )

        # Apply region filter if provided
        if region:
            publications = [
                pub
                for pub in publications
                if any(reg in pub.nuts_codes for reg in region)
            ]

        # Apply sector filter if provided
        if sector:
            # Extract first two digits of CPV code for sector filtering
            publications = [
                pub
                for pub in publications
                if any(pub.cpv_main_code_code[:2] + "000000" == sec for sec in sector)
            ]

        return paginate([
            await convert_publications_to_out_schema_list_free(publication=publication)
            for publication in publications
        ])


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
            session=session
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
        from app.util.kanban_integration import remove_unsaved_publication_from_kanban
        await remove_unsaved_publication_from_kanban(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session
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
