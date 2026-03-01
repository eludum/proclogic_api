from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from app.schemas.company_schemas import CompanyPublicationMatchSchema
from app.schemas.publication_contract_schemas import ContractSchema


class DescriptionSchema(BaseModel):
    language: str
    text: str
    model_config = ConfigDict(from_attributes=True)


class CPVCodeSchema(BaseModel):
    code: str
    descriptions: List[DescriptionSchema]

    model_config = ConfigDict(from_attributes=True)


class EnterpriseCategorySchema(BaseModel):
    category_code: str
    levels: List[int]

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel)


class DossierSchema(BaseModel):
    accreditations: Optional[dict] = None
    descriptions: List[DescriptionSchema]
    enterprise_categories: List[EnterpriseCategorySchema]
    legal_basis: str
    number: str
    procurement_procedure_type: Optional[str] = None
    reference_number: str
    special_purchasing_technique: Optional[str] = None
    titles: List[DescriptionSchema]

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel)


class LotSchema(BaseModel):
    descriptions: List[DescriptionSchema]
    reserved_execution: Optional[List[str]] = None
    reserved_participation: Optional[List[str]] = None
    titles: List[DescriptionSchema]

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel)


class OrganisationNameSchema(BaseModel):
    language: str
    text: str

    model_config = ConfigDict(from_attributes=True)


class OrganisationSchema(BaseModel):
    organisation_id: int
    organisation_names: List[OrganisationNameSchema]
    tree: str

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel)


class PublicationSchema(BaseModel):
    cpv_additional_codes: List[CPVCodeSchema]
    cpv_main_code: CPVCodeSchema
    dispatch_date: datetime
    dossier: DossierSchema
    insertion_date: datetime
    lots: List[LotSchema]
    natures: List[str]
    notice_ids: List[str]
    notice_sub_type: str
    nuts_codes: List[str]
    organisation: OrganisationSchema
    procedure_id: str
    publication_date: datetime
    publication_languages: List[str]
    publication_reference_numbers_bda: List[str] = Field(
        alias="publicationReferenceNumbersBDA"
    )
    publication_reference_numbers_ted: List[str] = Field(
        alias="publicationReferenceNumbersTED"
    )
    publication_type: str
    publication_workspace_id: str
    published_at: List[datetime]
    reference_number: str
    sent_at: List[datetime]
    ted_published: bool
    vault_submission_deadline: Optional[datetime] = None
    # forum: Optional[dict] = None
    ai_summary_without_documents: Optional[str] = None
    ai_summary_with_documents: Optional[str] = None
    contract: Optional[ContractSchema] = None

    estimated_value: Optional[int] = None
    extracted_keywords: Optional[List[str]] = Field(default_factory=list)

    company_matches: Optional[List[CompanyPublicationMatchSchema]] = Field(
        default_factory=list
    )

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel)
