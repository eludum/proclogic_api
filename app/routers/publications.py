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
from fastapi_pagination import Page, add_pagination, paginate

settings = Settings()
publications_router = APIRouter()
security = HTTPBearer()


@publications_router.get("/publications/", response_model=Page[PublicationOut])
async def get_publications(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all publications for an authenticated user"""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publications = crud_publication.get_all_publications(session=session)

        return paginate([
            await convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ])


@publications_router.get(
    "/publications/recommended/", response_model=Page[PublicationOut]
)
async def get_recommended_publications(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all publications recommended for the authenticated user's company"""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publications = crud_company.get_company_recommended_publications(
            company_vat_number=company.vat_number, session=session
        )

        return paginate([
            await convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ])


@publications_router.get("/publications/saved/", response_model=Page[PublicationOut])
async def get_saved_publications(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all publications saved by the authenticated user's company"""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publications = crud_company.get_company_saved_publications(
            company_vat_number=company.vat_number, session=session
        )

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
    "/publications/search/",
    response_model=Page[PublicationOut],
)
async def search_publications_paid(
    search_term: Optional[str] = Query(None, description="Search term"),
    auth_user: AuthUser = Depends(get_auth_user),
    region: List[str] = Query(None, description="Filter by region codes"),
    sector: List[str] = Query(None, description="Filter by sector"),
    cpv_code: List[str] = Query(None, description="Filter by CPV codes"),
    date_from: Optional[date] = Query(
        None, description="Filter publications from this date"
    ),
    date_to: Optional[date] = Query(
        None, description="Filter publications until this date"
    ),
) -> List[PublicationOut]:
    """Search publications with authentication (paid version)"""
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

        # Apply CPV code filter if provided
        if cpv_code:
            filtered_publications = []
            for pub in publications:
                # Check if main CPV code matches
                if pub.cpv_main_code_code in cpv_code:
                    filtered_publications.append(pub)
                    continue

                # Check if any additional CPV code matches
                if any(
                    additional_cpv.code in cpv_code
                    for additional_cpv in pub.cpv_additional_codes
                ):
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

        return paginate([
            await convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ])


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
    """Save a publication for the authenticated user's company"""
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

        success = crud_company.save_publication_for_company(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save publication")

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
    """Remove a publication from saved list for the authenticated user's company"""
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

        success = crud_company.unsave_publication_for_company(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication_workspace_id,
            session=session,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Publication was not saved")

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
