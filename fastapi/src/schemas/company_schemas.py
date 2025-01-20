from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SectorSchema(BaseModel):
    name: Optional[str]
    codes: List[str] = [""]

    ConfigDict(allow_arbitrary_types=True)


class CompanySchema(BaseModel):
    vat_number: str
    name: str
    interessed_sectors: List[SectorSchema]
    summary_activities: str

    model_config = ConfigDict(from_attributes=True)
