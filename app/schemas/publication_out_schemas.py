from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PublicationOut(BaseModel):
    title: str
    dispatch_date: datetime
    publication_date: datetime
    submission_deadline: Optional[datetime] = None
    is_active: Optional[bool] = None
    original_description: str
    ai_summary: str
    organisation: str
    cpv_code: str
    time_remaining: Optional[str] = None
    accreditations: Optional[dict] = None
    publication_value: str = None
    documents: Optional[List[str]] = None
    publication_in_your_sector: Optional[bool] = None
    is_recommended: bool
