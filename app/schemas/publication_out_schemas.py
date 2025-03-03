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
    ai_summary_without_documents: Optional[str] = None
    ai_summary_with_documents: Optional[str] = None
    organisation: str
    cpv_code: str
    cpv_additional_codes: Optional[List[str]] = None
    accreditations: Optional[dict] = None
    estimated_value: str = None
    documents: Optional[dict] = None
    publication_in_your_sector: Optional[bool] = None
    is_recommended: Optional[bool] = None
    is_saved: Optional[bool] = None
    region: Optional[List[str]] = None
    sector: str
