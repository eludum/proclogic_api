from typing import List

from app.config.settings import Settings
from app.schemas.publication_schemas import (DescriptionSchema,
                                             OrganisationNameSchema)

settings = Settings()


def get_descr_as_str(
    descriptions: List[DescriptionSchema],
    preferred_languages_descriptions=settings.prefered_languages_descriptions,
):
    # TODO: implement deepseek call to pick best description
    descr_text = ""
    for lang in preferred_languages_descriptions:
        for desc in descriptions:
            if desc.language == lang:
                descr_text = desc.text
    return "N/A" if not descr_text else descr_text


def get_org_name_as_str(
    organisation_names: List[OrganisationNameSchema],
    preferred_languages_descriptions=settings.prefered_languages_descriptions,
):
    for lang in preferred_languages_descriptions:
        for org_name in organisation_names:
            if org_name.language == lang:
                return org_name.text
    return "N/A"


def get_accreditations_as_str(accreditations: dict):
    return "\n".join(f"{key}, niveau(s) {value}" for key, value in accreditations.items())
