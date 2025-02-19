from typing import List

from fastapi import APIRouter

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.config.postgres import get_session
from app.crud.mapper import convert_publication_to_out_schema_with_company
from app.schemas.publication_out_schemas import PublicationOut

publications_router = APIRouter()

@publications_router.get(
    "/publications/{company_vatnumber}/", response_model=List[PublicationOut]
)
async def get_publications(
    company_vatnumber: str
) -> List[PublicationOut]:
    with get_session() as session:
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
