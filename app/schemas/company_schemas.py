from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class CompanyPublicationMatchSchema(BaseModel):
    publication_workspace_id: str
    company_vat_number: str
    match_percentage: float = 0.0
    is_recommended: bool = False
    is_saved: bool = False
    is_viewed: bool = False

    model_config = ConfigDict(from_attributes=True)


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
    publication_matches: Optional[List[CompanyPublicationMatchSchema]]

    model_config = ConfigDict(from_attributes=True)
