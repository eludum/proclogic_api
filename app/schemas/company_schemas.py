from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class SectorSchema(BaseModel):
    sector: str
    cpv_codes: List[str]

    model_config = ConfigDict(from_attributes=True)


class CompanySchema(BaseModel):
    vat_number: str
    name: str
    email: str
    interested_sectors: List[SectorSchema]
    summary_activities: str
    accreditations: Optional[dict]
    max_publication_value: Optional[int]

    model_config = ConfigDict(from_attributes=True)
