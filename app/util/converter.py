import logging
import re
from typing import List

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from pydantic import BaseModel

from app.config.settings import Settings
from app.schemas.publication_schemas import (
    DescriptionSchema,
    OrganisationNameSchema,
    PublicationSchema,
)

settings = Settings()


# Try to download NLTK data, with fallback if it fails
try:
    nltk.download("punkt", quiet=True)
    nltk.download("stopwords", quiet=True)
except:
    logging.warning("Could not download NLTK data. Keyword extraction will be limited.")


class LotInfo(BaseModel):
    title: str
    description: str


class PublicationInfo(BaseModel):
    dossier_desc_str: str = ""
    dossier_title_str: str = ""
    lots: list[LotInfo] = []
    lot_str: str = ""
    additional_cpv_codes_str: str = ""

    def convert_publication_to_str(self, publication: PublicationSchema):
        self.dossier_title_str = get_descr_as_str(publication.dossier.titles)
        self.dossier_desc_str = get_descr_as_str(publication.dossier.descriptions)

        self.lots = [
            LotInfo(
                title=f"{i + 1}. lot title: {get_descr_as_str(lot.titles)}",
                description=f"{i + 1}. lot description: {get_descr_as_str(lot.descriptions)}",
            )
            for i, lot in enumerate(publication.lots)
        ]

        self.lot_str = "\n".join(
            f"{lot.title} - {lot.description}" for lot in self.lots
        )

        self.additional_cpv_codes_str = ", ".join(
            cpv.code for cpv in publication.cpv_additional_codes
        )


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


def extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text for better matching."""
    try:
        # Simple tokenization and stopword removal
        tokens = word_tokenize(text.lower())
        stop_words = set(
            stopwords.words("english")
            + stopwords.words("dutch")
            + stopwords.words("french")
        )

        keywords = [
            word for word in tokens if word.isalnum() and word not in stop_words
        ]

        # Take only unique keywords
        return list(set(keywords))
    except:
        # Fallback if NLTK fails
        words = re.findall(r"\b\w+\b", text.lower())
        return list(set(words))


def truncate_text(text: str, max_length: int = 1000) -> str:
    """Truncate text to the specified max length."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
