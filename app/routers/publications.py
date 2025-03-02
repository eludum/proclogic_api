import logging
from typing import List

import httpx
from fastapi import APIRouter, HTTPException

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.config.postgres import get_session
from app.config.settings import Settings
from app.crud.mapper import convert_publication_to_out_schema_with_company
from app.schemas.publication_out_schemas import PublicationOut
from app.util.pubproc import get_publication_workspace_documents

settings = Settings()

publications_router = APIRouter()


@publications_router.get(
    "/publications/{company_vatnumber}/", response_model=List[PublicationOut]
)
async def get_publications(company_vatnumber: str) -> List[PublicationOut]:
    with get_session() as session:
        if not crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        ):
            raise HTTPException(status_code=404, detail="Company not found")
        
        publications = crud_publication.get_all_publications(session=session)

        company = crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        )

        return [
            convert_publication_to_out_schema_with_company(
                publication=publication, company=company
            )
            for publication in publications
        ]


@publications_router.get(
    "/publications/{company_vatnumber}/publication/{publication_workspace_id}/",
    response_model=PublicationOut,
)
async def get_publication_by_workspace_id(
    company_vatnumber: str,
    publication_workspace_id: str,
) -> PublicationOut:
    with get_session() as session:
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        company = crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        )
        
        return convert_publication_to_out_schema_with_company(
            publication=publication, company=company
        )


@publications_router.get(
    "/publications/{company_vatnumber}/search/{search_term}/",
    response_model=List[PublicationOut],
)
async def search_publications(
    company_vatnumber: str,
    search_term: str,
) -> List[PublicationOut]:
    with get_session() as session:
        publications = crud_publication.search_publications(
            search_term=search_term, session=session
        )

        company = crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        )

        return [
            convert_publication_to_out_schema_with_company(
                publication=publication, company=company
            )
            for publication in publications
        ]


@publications_router.get("/publications/{publication_id}/files")
async def get_publication_files(publication_id: str):
    """
    Get files for a publication by ID.
    This endpoint is used by the frontend to check available files.
    """
    try:
        async with httpx.AsyncClient() as client:
            filesmap = await get_publication_workspace_documents(client, publication_id)

            # Return only file names to avoid sending large file content
            file_names = {name: {"name": name} for name in filesmap.keys()}
            return file_names

    except Exception as e:
        logging.error(f"Error fetching publication files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# TODO: analytics endpoints, government entities and competitors, filter on sectors, make unified sectors router