from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.config.postgres import get_session
from app.config.settings import Settings
from app.crud.mapper import (convert_publication_to_out_schema_details_paid,
                             convert_publications_to_out_schema_list_free,
                             convert_publications_to_out_schema_list_paid)
from app.schemas.publication_out_schemas import PublicationOut
from app.util.clerk import AuthUser, get_auth_user

settings = Settings()
publications_router = APIRouter()
security = HTTPBearer()


@publications_router.get("/publications/", response_model=List[PublicationOut])
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

        return [
            convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ]


@publications_router.get(
    "/publications/publication/{publication_workspace_id}/",
    response_model=PublicationOut,
)
async def get_publication_by_workspace_id(
    publication_workspace_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
) -> PublicationOut:
    """Get a specific publication by workspace ID"""
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

        return convert_publication_to_out_schema_details_paid(
            publication=publication, company=company
        )


@publications_router.get(
    "/publications/free/search/{search_term}/",
    response_model=List[PublicationOut],
)
async def search_publications_free(
    search_term: str,
) -> List[PublicationOut]:
    """Search publications without authentication"""
    # TODO: add extra filters like region and cpv
    with get_session() as session:
        if not search_term:
            publications = crud_publication.get_all_publications(session=session)
            return [
                convert_publications_to_out_schema_list_free(publication=publication)
                for publication in publications
            ]
        else:
            publications = crud_publication.search_publications(
                search_term=search_term, session=session
            )

            return [
                convert_publications_to_out_schema_list_free(publication=publication)
                for publication in publications
            ]
