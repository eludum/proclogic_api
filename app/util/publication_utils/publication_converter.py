import logging
import re
from typing import List, Optional, Dict, Any, ClassVar
from pydantic import BaseModel, ConfigDict, Field, computed_field
from datetime import datetime
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from app.config.settings import Settings
from app.models.company_models import Company
from app.models.publication_models import Publication
from app.schemas.publication_out_schemas import PublicationOut
from app.schemas.publication_schemas import DescriptionSchema, OrganisationNameSchema
from app.util.publication_utils.nuts_codes import check_if_publication_is_in_your_region, get_nuts_code_as_str
from app.util.publication_utils.cpv_codes import check_if_publication_is_in_your_sector, get_cpv_sector_and_description

settings = Settings()

# Try to download NLTK data, with fallback if it fails
try:
    nltk.download("punkt", quiet=True)
    nltk.download("stopwords", quiet=True)
except:
    logging.warning("Could not download NLTK data. Keyword extraction will be limited.")


class PublicationText(BaseModel):
    """Pydantic model for textual content of a publication"""
    title: str
    description: str
    organisation_name: str
    lots_titles: List[str] = Field(default_factory=list)
    lots_descriptions: List[str] = Field(default_factory=list)
    additional_cpv_codes_str: str = ""
    
    model_config = ConfigDict(from_attributes=True)
    
    @computed_field
    def lots_text(self) -> str:
        """Combine lot titles and descriptions for easier text processing"""
        return "\n".join([f"{title}: {desc}" for title, desc in zip(self.lots_titles, self.lots_descriptions)])


class PublicationData(BaseModel):
    """Pydantic model for structured publication data"""
    workspace_id: str
    dispatch_date: datetime
    publication_date: datetime
    submission_deadline: Optional[datetime] = None
    cpv_code: str
    cpv_additional_codes: List[str] = Field(default_factory=list)
    nuts_codes: List[str] = Field(default_factory=list)
    accreditations: Optional[Dict[str, Any]] = None
    is_active: bool
    estimated_value: int = 0
    ai_summary_without_documents: Optional[str] = None
    ai_summary_with_documents: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
    
    @computed_field
    def region_names(self) -> List[str]:
        """Get human-readable region names from NUTS codes"""
        return [get_nuts_code_as_str(nuts_code) for nuts_code in self.nuts_codes]
    
    @computed_field
    def sector(self) -> str:
        """Get sector description from CPV code"""
        return get_cpv_sector_and_description(self.cpv_code, language="nl")


class MatchData(BaseModel):
    """Pydantic model for company-publication match data"""
    company_vat_number: str 
    is_recommended: bool = False
    is_saved: bool = False
    is_viewed: bool = False
    match_percentage: float = 0.0
    publication_in_sector: bool = False
    publication_in_region: bool = False
    
    model_config = ConfigDict(from_attributes=True)


class PublicationConverter(BaseModel):
    """Pydantic model for converting Publication models to various formats"""
    
    # Class variables for text processing
    preferred_languages: ClassVar[List[str]] = settings.prefered_languages_descriptions
    
    @staticmethod
    def get_descr_as_str(
        descriptions: List[DescriptionSchema],
        preferred_languages=settings.prefered_languages_descriptions,
    ) -> str:
        """Get the description text in a preferred language."""
        descr_text = ""
        for lang in preferred_languages:
            for desc in descriptions:
                if desc.language == lang:
                    descr_text = desc.text
        return "N/A" if not descr_text else descr_text

    @staticmethod
    def get_org_name_as_str(
        organisation_names: List[OrganisationNameSchema],
        preferred_languages=settings.prefered_languages_descriptions,
    ) -> str:
        """Get the organization name in a preferred language."""
        for lang in preferred_languages:
            for org_name in organisation_names:
                if org_name.language == lang:
                    return org_name.text
        return "N/A"

    @staticmethod
    def get_accreditations_as_str(accreditations: dict) -> str:
        """Format accreditations as a string."""
        if not accreditations:
            return "None"
        return "\n".join(
            f"{key}, niveau(s) {value}" for key, value in accreditations.items()
        )

    @staticmethod
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

    @staticmethod
    def truncate_text(text: str, max_length: int = 1000) -> str:
        """Truncate text to the specified max length."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
    
    @classmethod
    def extract_text(cls, publication: Publication) -> PublicationText:
        """Extract all text content from a publication"""
        return PublicationText(
            title=cls.get_descr_as_str(publication.dossier.titles),
            description=cls.get_descr_as_str(publication.dossier.descriptions),
            organisation_name=cls.get_org_name_as_str(publication.organisation.organisation_names),
            lots_titles=[cls.get_descr_as_str(lot.titles) for lot in publication.lots],
            lots_descriptions=[cls.get_descr_as_str(lot.descriptions) for lot in publication.lots],
            additional_cpv_codes_str=", ".join(cpv.code for cpv in publication.cpv_additional_codes)
        )
    
    @classmethod
    def extract_data(cls, publication: Publication) -> PublicationData:
        """Extract structured data from a publication"""
        return PublicationData(
            workspace_id=publication.publication_workspace_id,
            dispatch_date=publication.dispatch_date,
            publication_date=publication.publication_date,
            submission_deadline=publication.vault_submission_deadline,
            cpv_code=publication.cpv_main_code.code,
            cpv_additional_codes=[cpv.code for cpv in publication.cpv_additional_codes],
            nuts_codes=publication.nuts_codes,
            accreditations=publication.dossier.accreditations,
            is_active=publication.is_active,
            estimated_value=publication.estimated_value if publication.estimated_value else 0,
            ai_summary_without_documents=publication.ai_summary_without_documents,
            ai_summary_with_documents=publication.ai_summary_with_documents
        )
    
    @classmethod
    def extract_match_data(cls, publication: Publication, company: Company) -> MatchData:
        """Extract match data between a publication and a company"""
        match_data = MatchData(company_vat_number=company.vat_number)
        
        # Find matching record if it exists
        for match in publication.company_matches:
            if match.company_vat_number == company.vat_number:
                match_data.is_recommended = match.is_recommended
                match_data.is_saved = match.is_saved
                match_data.is_viewed = match.is_viewed
                match_data.match_percentage = match.match_percentage
                break
        
        # Calculate sector and region matches
        pub_data = cls.extract_data(publication)
        match_data.publication_in_sector = check_if_publication_is_in_your_sector(
            company.interested_sectors, pub_data.cpv_code
        )
        match_data.publication_in_region = check_if_publication_is_in_your_region(
            company.operating_regions, pub_data.nuts_codes
        )
        
        return match_data
    
    @classmethod
    def to_output_schema(
        cls,
        publication: Publication, 
        company: Optional[Company] = None,
        documents: Optional[Dict[str, Any]] = None,
        forum: Optional[Dict[str, Any]] = None
    ) -> PublicationOut:
        """Convert a publication to the PublicationOut schema"""
        pub_text = cls.extract_text(publication)
        pub_data = cls.extract_data(publication)
        
        # Create the base output schema
        output = PublicationOut(
            title=pub_text.title,
            workspace_id=pub_data.workspace_id,
            dispatch_date=pub_data.dispatch_date,
            publication_date=pub_data.publication_date,
            submission_deadline=pub_data.submission_deadline,
            is_active=pub_data.is_active,
            original_description=pub_text.description,
            organisation=pub_text.organisation_name,
            cpv_code=pub_data.cpv_code,
            cpv_additional_codes=pub_data.cpv_additional_codes,
            accreditations=pub_data.accreditations,
            region=pub_data.region_names,
            sector=pub_data.sector,
            lots=pub_text.lots_titles,
            estimated_value=pub_data.estimated_value,
            ai_summary_without_documents=pub_data.ai_summary_without_documents,
            ai_summary_with_documents=pub_data.ai_summary_with_documents,
        )
        
        # Add company-specific data if a company is provided
        if company:
            match_data = cls.extract_match_data(publication, company)
            
            output.is_recommended = match_data.is_recommended
            output.match_percentage = match_data.match_percentage
            output.is_saved = match_data.is_saved
            output.is_viewed = match_data.is_viewed
            output.publication_in_your_sector = match_data.publication_in_sector
            output.publication_in_your_region = match_data.publication_in_region
        
        # Add documents and forum data if provided
        if documents:
            output.documents = documents
            
        if forum:
            output.forum = forum
            
        return output
    
    @classmethod
    def to_xml_summary_input(cls, publication: Publication) -> str:
        """Create a text summary of the publication for XML processing"""
        pub_text = cls.extract_text(publication)
        
        return (
            f"Main CPV code: {publication.cpv_main_code.code}. "
            f"Additional CPV codes: {pub_text.additional_cpv_codes_str}. "
            f"Title: {pub_text.title}. "
            f"Description: {pub_text.description}. "
            f"Lots: {', '.join(pub_text.lots_titles)}. "
        )
    
    @classmethod
    def to_recommendation_input(cls, publication: Publication, company: Company) -> str:
        """Create input for recommendation systems"""
        pub_text = cls.extract_text(publication)
        
        interested_sectors_as_cpv_str = ", ".join(
            f"{sector.sector}: {sector.cpv_codes}" for sector in company.interested_sectors
        )
        
        return (
            f"The company {company.name} specializes in {company.summary_activities}. "
            f"Accreditations: {cls.get_accreditations_as_str(company.accreditations) if company.accreditations else 'not found in database'}. "
            f"Max publication value: {company.max_publication_value if company.max_publication_value else 'not found in database'}. "
            f"Interested CPV codes: {interested_sectors_as_cpv_str}. "
            f"Publication CPV codes: Main {publication.cpv_main_code.code}, Additional {pub_text.additional_cpv_codes_str}. "
            f"Title: {pub_text.title}. "
            f"Description: {pub_text.description}. "
            f"Lots: {', '.join(pub_text.lots_titles)}. "
        )
