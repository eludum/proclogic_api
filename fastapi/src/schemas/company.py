from typing import List

from pydantic import BaseModel

from schemas.sector_schemas import Sector


class Company(BaseModel):
    name: str
    vat_number: str
    interessed_sectors: List[Sector]
    summary_activities: str
