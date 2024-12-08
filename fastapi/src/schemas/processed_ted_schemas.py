from pydantic import BaseModel
from schemas.company import Company
from ted_schemas import Notice


class ProcessedNotice(BaseModel):
    notice: Notice
    company: Company
    recommended: bool
