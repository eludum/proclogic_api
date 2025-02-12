# TODO: map sqlalchemy objects back to pydantic

from app.config.settings import Settings
from app.models.publication_models import Company, Publication
from app.schemas.publication_out_schemas import PublicationOut

settings = Settings()


def get_descr_as_str(
    descriptions,
    preferred_languages_descriptions=settings.prefered_languages_descriptions,
):
    # TODO: implement deepseek call to pick best description
    descr_text = ""
    for lang in preferred_languages_descriptions:
        for desc in descriptions:
            if desc.language == lang:
                descr_text = desc.text
    return "N/A" if not descr_text else descr_text


def convert_publication_to_out_schema(
    publication: Publication, company: Company
) -> PublicationOut:

    for org_name in publication.organisation.organisation_names:
        if org_name.language == "en":
            parsed_org_name = org_name.text

    # TODO: add publication docs and value (get from workspace niffo), time remaining and isactive, lots, in your sector
    pub_out = PublicationOut(
        title=get_descr_as_str(publication.dossier.titles),
        dispatch_date=publication.dispatch_date,
        publication_date=publication.publication_date,
        submission_deadline=publication.vault_submission_deadline,
        is_active=publication.is_active,
        original_description=get_descr_as_str(publication.dossier.descriptions),
        ai_summary=publication.ai_summary,
        organisation=parsed_org_name,
        cpv_code=publication.cpv_main_code_code,
        accreditations=publication.dossier.accreditations,
        is_recommended=True if company in publication.recommended_companies else False,
    )

    return pub_out
