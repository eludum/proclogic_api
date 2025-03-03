# TODO: map sqlalchemy objects back to pydantic

import httpx
from app.config.settings import Settings
from app.models.company_models import Company, Sector
from app.models.publication_models import Publication
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_out_schemas import PublicationOut
from app.util.nuts_codes import get_nuts_code_as_str
from app.util.cpv_codes import get_cpv_sector_and_description
from app.util.pubproc import get_publication_workspace_documents

from app.util.converter import get_descr_as_str, get_org_name_as_str


settings = Settings()

async def convert_publication_to_out_schema_free(
    publication: Publication
) -> PublicationOut:
    
    # TODO: add publication docs and value (get from workspace niffo) and isactive check date, lots, in your sector

    async with httpx.AsyncClient() as client:
        documents = await get_publication_workspace_documents(client, publication.publication_workspace_id)

    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.vault_submission_deadline is not None,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes],
        accreditations=publication.dossier.accreditations,
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(publication.cpv_main_code.code, language="nl"),
        documents=get_publication_workspace_documents(documents)
    )

    return pub_out


async def convert_publication_to_out_schema_with_company_paid(
    publication: Publication, company: Company
) -> PublicationOut:
    
    # TODO: add publication docs and value (get from workspace niffo) and isactive check date, lots, in your sector

    async with httpx.AsyncClient() as client:
        documents = await get_publication_workspace_documents(client, publication.publication_workspace_id)

    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.vault_submission_deadline is not None,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        ai_summary_without_documents=publication.ai_summary_without_documents,
        ai_summary_with_documents=publication.ai_summary_with_documents,
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes],
        accreditations=publication.dossier.accreditations,
        is_recommended=True if company in publication.recommended_companies else False,
        is_saved=True if company in publication.saved_companies else False,
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(publication.cpv_main_code.code, language="nl"),
        estimated_value=publication.estimated_value
        documents=publication.documents
    )

    return pub_out


async def convert_company_to_schema(company: Company) -> CompanySchema:
    """Convert a SQLAlchemy Company model instance to a Pydantic CompanySchema."""
    return CompanySchema(
        vat_number=company.vat_number,
        name=company.name,
        email=company.email,
        interested_sectors=[
            Sector(
                sector=sector.sector,
                cpv_codes=sector.cpv_codes
            )
            for sector in company.interested_sectors
        ],
        summary_activities=company.summary_activities,
        accreditations=company.accreditations,
        max_publication_value=company.max_publication_value,
    )
