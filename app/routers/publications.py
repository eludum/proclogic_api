from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.config.postgres import get_session_generator
from app.crud.mapper import convert_publication_to_out_schema_with_company
from app.schemas.publication_out_schemas import PublicationOut

publications_router = APIRouter()


@publications_router.get("/publications/{company_vatnumber}/", response_model=List[PublicationOut])
async def get_publications_by_vat(
    company_vatnumber: str, session: Session = Depends(get_session_generator)
) -> List[PublicationOut]:
    publications = crud_publication.get_all_publications(  # or planning publications
        session=session
    )

    company = crud_company.get_company_by_vat_number(
        vat_number=company_vatnumber, session=session
    )

    # TODO: filter on VAULT SUBMISSION DEADLINE TO SEE IF ACTIVE ALSO SUBMISSION DEADLINE
    return [
        convert_publication_to_out_schema_with_company(
            publication=publication, company=company
        )
        for publication in publications
    ]


@publications_router.get("/publication/{publication_workspace_id}/", response_model=PublicationOut)
async def get_publication_by_workspace_id(
    publication_workspace_id: str, session: Session = Depends(get_session_generator)
) -> PublicationOut:
    publication = crud_publication.get_publication_by_workspace_id(
        publication_workspace_id=publication_workspace_id, session=session
    )
    return convert_publication_to_out_schema_with_company(
        publication=publication, company=None
    )


@publications_router.get("/publications/search/{search_term}/", response_model=List[PublicationOut])
async def search_publications(
    search_term: str, session: Session = Depends(get_session_generator)
) -> List[PublicationOut]:
    publications = crud_publication.search_publications(
        search_term=search_term, session=session
    )

    return [
        convert_publication_to_out_schema_with_company(
            publication=publication, company=None
        )
        for publication in publications
    ]
