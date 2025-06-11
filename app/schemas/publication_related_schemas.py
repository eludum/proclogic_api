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


class RelatedPublicationItem(BaseModel):
    """Schema for related active publications"""
    workspace_id: str
    title: str
    organisation: str
    publication_date: datetime
    submission_deadline: Optional[datetime]
    cpv_code: str
    sector: str
    estimated_value: Optional[int]
    similarity_score: float
    similarity_reason: str
    match_percentage: Optional[float] = None  # If user is authenticated

    model_config = ConfigDict(from_attributes=True)


class RelatedContentResponse(BaseModel):
    """Response schema for related content"""
    related_contracts: List[RelatedContractItem]
    total_contracts: int

    model_config = ConfigDict(from_attributes=True)
