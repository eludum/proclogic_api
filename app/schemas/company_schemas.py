from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.models.publication_models import CompanyPublicationMatch


class SectorSchema(BaseModel):
    sector: str
    cpv_codes: List[str]

    model_config = ConfigDict(from_attributes=True)


class CompanySchema(BaseModel):
    vat_number: str
    subscription: str
    name: str
    emails: List[str]
    interested_sectors: List[SectorSchema]
    summary_activities: str
    accreditations: Optional[dict]
    max_publication_value: Optional[int]
    activity_keywords: Optional[List[str]] = []
    operating_regions: Optional[List[str]] = []
    publication_matches: Optional[List[CompanyPublicationMatch]]

    model_config = ConfigDict(from_attributes=True)
