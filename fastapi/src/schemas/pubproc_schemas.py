from typing import List, Optional
from pydantic import BaseModel

class Description(BaseModel):
    language: str
    text: str

class CPVCode(BaseModel):
    code: str
    descriptions: List[Description]

class Dossier(BaseModel):
    accreditations: dict
    descriptions: List[Description]
    enterpriseCategories: List[str]
    legalBasis: str
    number: str
    procurementProcedureType: str
    referenceNumber: str
    specialPurchasingTechnique: Optional[str]
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
    vaultSubmissionDeadline: str

class Publications(BaseModel):
    totalCount: int
    publications: List[Publication]

# Example usage
# data = {...}  # Your JSON data
# publications = Publications(**data)
