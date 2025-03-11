import httpx

from app.config.settings import Settings
from app.models.company_models import Company
from app.models.publication_models import Publication
from app.schemas.company_schemas import CompanySchema, SectorSchema
from app.schemas.publication_out_schemas import PublicationOut
from app.schemas.publication_schemas import CompanyPublicationMatchSchema
from app.util.converter import get_descr_as_str, get_org_name_as_str
from app.util.cpv_codes import (
    check_if_publication_is_in_your_sector,
    get_cpv_sector_and_description,
)
from app.util.nuts_codes import check_if_publication_is_in_your_region, get_nuts_code_as_str
from app.util.pubproc import (
    get_publication_workspace_documents,
    get_publication_workspace_forum,
)


settings = Settings()


async def convert_publications_to_out_schema_list_free(
    publication: Publication,
) -> PublicationOut:

    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.is_active,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes
        ],
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(
            publication.cpv_main_code.code, language="nl"
        ),
        lots=[get_descr_as_str(lot.titles) for lot in publication.lots],
    )

    return pub_out


async def convert_publications_to_out_schema_list_paid(
    company: Company, publication: Publication
) -> PublicationOut:

    is_recommended = False
    is_saved = False
    is_viewed = False
    match_percentage = 0.0
    for match in publication.company_matches:
        if match.company_vat_number == company.vat_number:
            is_recommended = match.is_recommended
            is_saved = match.is_saved
            is_viewed = match.is_viewed
            match_percentage = match.match_percentage
            break

    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.is_active,
        publication_in_your_sector=check_if_publication_is_in_your_sector(
            company.interested_sectors, publication.cpv_main_code.code
        ),
        is_recommended=is_recommended,
        match_percentage=match_percentage,
        is_saved=is_saved,
        is_viewed=is_viewed,
        publication_in_your_region=check_if_publication_is_in_your_region(
            company.operating_regions, publication.nuts_codes
        ),
        original_description=get_descr_as_str(publication.dossier.descriptions),
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes
        ],
        accreditations=publication.dossier.accreditations,
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(
            publication.cpv_main_code.code, language="nl"
        ),
        lots=[get_descr_as_str(lot.titles) for lot in publication.lots],
        estimated_value=(
            publication.estimated_value if publication.estimated_value else 0
        ),
    )

    return pub_out


async def convert_publication_to_out_schema_details_free(
    publication: Publication,
) -> PublicationOut:

    async with httpx.AsyncClient() as client:
        documents = await get_publication_workspace_documents(
            client, publication.publication_workspace_id
        )
        forum = await get_publication_workspace_forum(
            client, publication.publication_workspace_id
        )

    serializable_documents = {}
    if documents:
        for filename, file_data in documents.items():
            serializable_documents[filename] = {
                "filename": filename,
                # "content": file_data,
            }

    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.is_active,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes
        ],
        accreditations=publication.dossier.accreditations,
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(
            publication.cpv_main_code.code, language="nl"
        ),
        lots=[get_descr_as_str(lot.titles) for lot in publication.lots],
        documents=serializable_documents,  # TODO: limit these two
        forum=forum,
    )

    return pub_out


async def convert_publication_to_out_schema_details_paid(
    publication: Publication, company: Company
) -> PublicationOut:

    is_recommended = False
    is_saved = False
    is_viewed = False
    match_percentage = 0.0
    for match in publication.company_matches:
        if match.company_vat_number == company.vat_number:
            is_recommended = match.is_recommended
            is_saved = match.is_saved
            is_viewed = match.is_viewed
            match_percentage = match.match_percentage
            break

    async with httpx.AsyncClient() as client:
        documents = await get_publication_workspace_documents(
            client, publication.publication_workspace_id
        )
        forum = await get_publication_workspace_forum(
            client, publication.publication_workspace_id
        )

    serializable_documents = {}
    if documents:
        for filename, file_data in documents.items():
            serializable_documents[filename] = {
                "filename": filename,
                # "content": file_data,
            }

    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.is_active,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        ai_summary_without_documents=publication.ai_summary_without_documents,
        ai_summary_with_documents=publication.ai_summary_with_documents,
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes
        ],
        accreditations=publication.dossier.accreditations,
        publication_in_your_sector=check_if_publication_is_in_your_sector(
            company.interested_sectors, publication.cpv_main_code.code
        ),
        is_recommended=is_recommended,
        match_percentage=match_percentage,
        is_saved=is_saved,
        is_viewed=is_viewed,
        publication_in_your_region=check_if_publication_is_in_your_region(
            company.operating_regions, publication.nuts_codes
        ),
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(
            publication.cpv_main_code.code, language="nl"
        ),
        lots=[get_descr_as_str(lot.titles) for lot in publication.lots],
        estimated_value=(
            publication.estimated_value if publication.estimated_value else 0
        ),
        documents=serializable_documents,
        forum=forum,
    )

    return pub_out


async def convert_company_to_schema(company: Company) -> CompanySchema:
    """Convert a SQLAlchemy Company model instance to a Pydantic CompanySchema."""

    return CompanySchema(
        vat_number=company.vat_number,
        subscription=company.subscription,
        name=company.name,
        emails=company.emails,
        interested_sectors=[
            SectorSchema(sector=sector.sector, cpv_codes=sector.cpv_codes)
            for sector in company.interested_sectors
        ],
        accreditations=company.accreditations,
        summary_activities=company.summary_activities,
        max_publication_value=company.max_publication_value,
        activity_keywords=company.activity_keywords,
        operating_regions=company.operating_regions,
        publication_matches=[
            CompanyPublicationMatchSchema(
                publication_workspace_id=match.publication_workspace_id,
                company_vat_number=match.company_vat_number,
                is_recommended=match.is_recommended,
                is_saved=match.is_saved,
                is_viewed=match.is_viewed,
                match_percentage=match.match_percentage,
            )
            for match in company.publication_matches
        ],
    )
