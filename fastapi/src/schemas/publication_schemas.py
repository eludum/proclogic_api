from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class DescriptionSchema(BaseModel):
    language: str
    text: str


class CPVCodeSchema(BaseModel):
    code: str
    descriptions: List[DescriptionSchema]
    sector_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CompanySchema(BaseModel):
    vat_number: str
    name: str
    email: str
    interested_cpv_codes: List[CPVCodeSchema]
    summary_activities: str

    model_config = ConfigDict(from_attributes=True)


class EnterpriseCategorySchema(BaseModel):
    categoryCode: str
    levels: List[int]


class DossierSchema(BaseModel):
    accreditations: Optional[dict] = None
    descriptions: List[DescriptionSchema]
    enterpriseCategories: List[EnterpriseCategorySchema]
    legalBasis: str
    number: str
    procurementProcedureType: Optional[str] = None
    referenceNumber: str
    specialPurchasingTechnique: Optional[str] = None
    titles: List[DescriptionSchema]

    model_config = ConfigDict(from_attributes=True)


class LotSchema(BaseModel):
    descriptions: List[DescriptionSchema]
    reservedExecution: List[str]
    reservedParticipation: List[str]
    titles: List[DescriptionSchema]

    model_config = ConfigDict(from_attributes=True)


class OrganisationNameSchema(BaseModel):
    language: str
    text: str


class OrganisationSchema(BaseModel):
    organisationId: int
    organisationNames: List[OrganisationNameSchema]
    tree: str

    model_config = ConfigDict(from_attributes=True)


class PublicationSchema(BaseModel):
    cpvAdditionalCodes: List[CPVCodeSchema]
    cpvMainCode: CPVCodeSchema
    dispatchDate: datetime
    dossier: DossierSchema
    insertionDate: datetime
    lots: List[LotSchema]
    natures: List[str]
    noticeIds: List[str]
    noticeSubType: str
    nutsCodes: List[str]
    organisation: OrganisationSchema
    procedureId: str
    publicationDate: datetime
    publicationLanguages: List[str]
    publicationReferenceNumbersBDA: List[str]
    publicationReferenceNumbersTED: List[str]
    publicationType: str
    publicationWorkspaceId: str
    publishedAt: List[datetime]
    referenceNumber: str
    sentAt: List[datetime]
    tedPublished: bool
    vaultSubmissionDeadline: Optional[datetime] = None
    recommended: Optional[List[CompanySchema]] = None
    ai_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
