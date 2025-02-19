# TODO: map sqlalchemy objects back to pydantic

from app.config.settings import Settings
from app.models.company_models import Company, Sector
from app.models.publication_models import Publication
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_out_schemas import PublicationOut
from app.util.nuts_codes import get_nuts_code_as_str
from app.util.cpv_codes import get_cpv_sector_and_description

from app.util.converter import get_descr_as_str, get_org_name_as_str


settings = Settings()


def convert_publication_to_out_schema_with_company(
    publication: Publication, company: Company
) -> PublicationOut:
    
    # TODO: add publication docs and value (get from workspace niffo), time remaining and isactive, lots, in your sector
    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        workspace_id=publication.publication_workspace_id,
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.vault_submission_deadline is not None,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        ai_notice_summary=publication.ai_notice_summary,
        ai_document_summary=publication.ai_document_summary,
        organisation=get_org_name_as_str(publication.organisation.organisation_names),
        cpv_code=publication.cpv_main_code_code,
        cpv_additional_codes=[
            cpv_code.code for cpv_code in publication.cpv_additional_codes],
        accreditations=publication.dossier.accreditations,
        is_recommended=True if company in publication.recommended_companies else False,
        region=[
            get_nuts_code_as_str(nuts_code) for nuts_code in publication.nuts_codes
        ],
        sector=get_cpv_sector_and_description(publication.cpv_main_code.code)[1],
    )

    return pub_out


def convert_company_to_schema(company: Company) -> CompanySchema:
    """Convert a SQLAlchemy Company model instance to a Pydantic CompanySchema."""
    return CompanySchema(
        vat_number=company.vat_number,
        name=company.name,
        email=company.email,
        interested_cpv_codes=[
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
