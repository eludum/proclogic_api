from pydantic import BaseModel
from typing import List
from util.sectors import Sector


class Company(BaseModel):
    name: str
    vat_number: str
    interessed_sectors: List[Sector]
    summary_activities: str
