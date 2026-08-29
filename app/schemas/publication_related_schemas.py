from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class RelatedContractItem(BaseModel):
    """Schema for related awarded contracts"""
    publication_id: str
    title: str
    award_date: Optional[datetime]
    winner: str
    value: float
    sector: str
    cpv_code: str
    buyer: str
    similarity_score: float
    similarity_reason: str

    model_config = ConfigDict(from_attributes=True)


class RelatedContentResponse(BaseModel):
    """Response schema for related content.

    ``source`` exists so the page can say which engine produced the list rather
    than implying the model read the database when it did not. "rules" is the
    instant CPV/buyer/region comparison; "procy" means the retrieval agent
    actually searched the awards and wrote each reason itself.
    """

    related_contracts: List[RelatedContractItem]
    total_contracts: int

    # "rules" | "procy"
    source: str = "rules"
    # "ready" | "running" | "none" -- the state of a deep search for this tender,
    # so the client knows whether to offer the button, poll, or do nothing.
    deep_status: str = "none"

    model_config = ConfigDict(from_attributes=True)
