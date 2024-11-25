from pydantic import BaseModel
from ted_schemas import Notice
from util.sectors import Sector


class ProcessedNotice(BaseModel):
    notice: Notice
    summary: str
    sector: Sector
