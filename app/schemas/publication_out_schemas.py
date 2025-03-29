from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PublicationOut(BaseModel):
    # Basic information about the publication
    title: str
    workspace_id: str
    dispatch_date: datetime
    publication_date: datetime
    submission_deadline: Optional[datetime] = None
    is_active: Optional[bool]

    # Description and summaries
    original_description: str
    ai_summary_without_documents: Optional[str] = None
    ai_summary_with_documents: Optional[str] = None

    # Organisation and CPV information
    organisation: str
    cpv_code: str
    cpv_additional_codes: Optional[List[str]] = None

    # Additional information
    accreditations: Optional[dict] = None
    estimated_value: int = 0
    documents: Optional[dict] = None
    # TODO: add external links
    external_links: Optional[str] = None

    # User-specific information
    publication_in_your_sector: Optional[bool] = None
    is_recommended: Optional[bool] = None
    match_percentage: Optional[float] = None
    is_saved: Optional[bool] = None
    is_viewed: Optional[bool] = None
    publication_in_your_region: Optional[bool] = None

    # Location and sector information
    region: Optional[List[str]] = None
    sector: str

    # Lot information
    lot_titles: Optional[List[str]] = None
    lot_descriptions: Optional[List[str]] = None

    # Forum information
    # forum: Optional[dict] = None
