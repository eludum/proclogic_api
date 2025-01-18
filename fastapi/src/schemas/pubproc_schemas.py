from typing import List, Optional
from pydantic import BaseModel


class Description(BaseModel):
    language: str
    text: str


class CPVCode(BaseModel):
    code: str
    descriptions: List[Description]


class EnterpriseCategory(BaseModel):
    categoryCode: str
    levels: List[int]


class Dossier(BaseModel):
    accreditations: Optional[dict] = None
    descriptions: List[Description]
    enterpriseCategories: List[EnterpriseCategory]
    legalBasis: str
    number: str
    procurementProcedureType: Optional[str] = None
    referenceNumber: str
    specialPurchasingTechnique: Optional[str] = None
    titles: List[Description]


class Lot(BaseModel):
    descriptions: List[Description]
    reservedExecution: List[str]
    reservedParticipation: List[str]
    titles: List[Description]


class OrganisationName(BaseModel):
    language: str
    text: str


class Organisation(BaseModel):
    organisationId: int
    organisationNames: List[OrganisationName]
    tree: str


class Publication(BaseModel):
    cpvAdditionalCodes: List[CPVCode]
    cpvMainCode: CPVCode
    dispatchDate: str
    dossier: Dossier
    insertionDate: str
    lots: List[Lot]
    natures: List[str]
    noticeIds: List[str]
    noticeSubType: str
    nutsCodes: List[str]
    organisation: Organisation
    procedureId: str
    publicationDate: str
    publicationLanguages: List[str]
    publicationReferenceNumbersBDA: List[str]
    publicationReferenceNumbersTED: List[str]
    publicationType: str
    publicationWorkspaceId: str
    publishedAt: List[str]
    referenceNumber: str
    sentAt: List[str]
    tedPublished: bool
    vaultSubmissionDeadline: Optional[str] = None
