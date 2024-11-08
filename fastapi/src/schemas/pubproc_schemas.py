from typing import List
from pydantic import BaseModel


class OrganisationName(BaseModel):
    text: str
    language: str


class Organisation(BaseModel):
    organisationId: int
    tree: str
    organisationNames: List[OrganisationName]


class Title(BaseModel):
    text: str
    language: str


class Description(BaseModel):
    text: str
    language: str


class Accreditations(BaseModel):
    additionalProp1: int
    additionalProp2: int
    additionalProp3: int


class Dossier(BaseModel):
    titles: List[Title]
    descriptions: List[Description]
    accreditations: Accreditations
    referenceNumber: str
    procurementProcedureType: str
    specialPurchasingTechnique: str
    legalBasis: str


class Description1(BaseModel):
    text: str
    language: str


class Lot(BaseModel):
    titles: List[Title]
    descriptions: List[Description1]
    reservedParticipation: List[str]
    reservedExecution: List[str]


class CpvMainCode(BaseModel):
    code: str
    descriptions: List[Description]


class CpvAdditionalCode(BaseModel):
    code: str
    descriptions: List[Description]


class Publication(BaseModel):
    id: int
    referenceNumber: str
    insertionDate: str
    organisation: Organisation
    cancelledAt: str
    dossier: Dossier
    lots: List[Lot]
    publicationWorkspaceId: str
    cpvMainCode: CpvMainCode
    cpvAdditionalCodes: List[CpvAdditionalCode]
    natures: List[str]
    publicationLanguages: List[str]
    nutsCodes: List[str]
    dispatchDate: str
    sentAt: List[str]
    publishedAt: List[str]
    vaultSubmissionDeadline: str
    tedPublished: str
    noticeSubType: str
    noticeIds: List[str]
    procedureId: str


class Model(BaseModel):
    totalCount: int
    publications: List[Publication]
