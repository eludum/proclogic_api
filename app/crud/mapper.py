# TODO: map sqlalchemy objects back to pydantic

from app.config.settings import Settings
from app.models.publication_models import Company, Publication
from app.schemas.publication_out_schemas import PublicationOut
from app.models.publication_models import Company
from app.schemas.publication_schemas import (
    CPVCodeSchema,
    CompanySchema,
    DescriptionSchema,
)
from app.util.converter import get_descr_as_str

settings = Settings()


def convert_publication_to_out_schema(
    publication: Publication, company: Company
) -> PublicationOut:

    parsed_org_name = ""
    for org_name in publication.organisation.organisation_names:
        if org_name.language == "en":
            parsed_org_name = org_name.text

    # TODO: add publication docs and value (get from workspace niffo), time remaining and isactive, lots, in your sector
    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.vault_submission_deadline is not None,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        ai_summary=publication.ai_summary,
        organisation=parsed_org_name,
        cpv_code=publication.cpv_main_code_code,
        accreditations=publication.dossier.accreditations,
        is_recommended=True if company in publication.recommended_companies else False,
    )

    return pub_out


def convert_company_to_schema(company: Company) -> CompanySchema:
    """Convert a SQLAlchemy Company model instance to a Pydantic CompanySchema."""
    return CompanySchema(
        vat_number=company.vat_number,
        name=company.name,
        email=company.email,
        interested_cpv_codes=[
            CPVCodeSchema(
                code=cpv_code.code,
                descriptions=[
                    DescriptionSchema(language=desc.language, text=desc.text)
                    for desc in cpv_code.descriptions
                ],
            )
            for cpv_code in company.interested_cpv_codes
        ],
        summary_activities=company.summary_activities,
        accreditations=company.accreditations,
        max_publication_value=company.max_publication_value,
    )
