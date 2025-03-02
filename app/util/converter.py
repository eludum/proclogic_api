from typing import List

from pydantic import BaseModel

from app.config.settings import Settings
from app.schemas.publication_schemas import (
    DescriptionSchema,
    OrganisationNameSchema,
    PublicationSchema,
)

settings = Settings()


def get_descr_as_str(
    descriptions: List[DescriptionSchema],
    preferred_languages_descriptions=settings.prefered_languages_descriptions,
):
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
    return "\n".join(
        f"{key}, niveau(s) {value}" for key, value in accreditations.items()
    )


class PublicationInfo(BaseModel):
    dossier_desc_str: str = ""
    dossier_title_str: str = ""
    lot_desc_str: str = ""
    lot_title_str: str = ""
    additional_cpv_codes_str: str = ""

    def convert_publication_to_str(self, publication: PublicationSchema):
        self.dossier_title_str = get_descr_as_str(publication.dossier.titles)

        self.dossier_desc_str = get_descr_as_str(publication.dossier.descriptions)

        self.lot_title_str = ""
        self.lot_desc_str = ""
        for i, lot in enumerate(publication.lots):
            if i < len(publication.lots) - 1:
                self.lot_title_str += (
                    str(i + 1)
                    + ". lot title: "
                    + get_descr_as_str(lot.titles)
                    + ", "
                    + "\n"
                )

                self.lot_desc_str += (
                    str(i + 1)
                    + ". lot description: "
                    + get_descr_as_str(lot.descriptions)
                    + ", "
                    + "\n"
                )
            else:
                self.lot_title_str += (
                    str(i + 1) + ". lot title: " + get_descr_as_str(lot.titles) + "\n"
                )

                self.lot_desc_str += (
                    str(i + 1)
                    + ". lot description: "
                    + get_descr_as_str(lot.descriptions)
                    + "\n"
                )

        self.additional_cpv_codes_str = ", ".join(
            cpv_code.code for cpv_code in publication.cpv_additional_codes
        )
