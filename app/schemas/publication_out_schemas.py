from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PublicationOut(BaseModel):
    title: str
    workspace_id: str
    dispatch_date: datetime
    publication_date: datetime
    submission_deadline: Optional[datetime] = None
    is_active: Optional[bool] = None
    original_description: str
    ai_notice_summary: Optional[str] = None
    organisation: str
    cpv_code: str
    cpv_additional_codes: Optional[List[str]] = None
    time_remaining: Optional[str] = None
    accreditations: Optional[dict] = None
    publication_value: str = None
    documents: Optional[List[str]] = None
    publication_in_your_sector: Optional[bool] = None
    is_recommended: bool
    region: Optional[List[str]] = None
    sector: str
    