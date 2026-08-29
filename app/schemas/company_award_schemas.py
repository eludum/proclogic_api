"""Schemas for company-supplied award data.

Note what is absent: no company_vat_number and no created_by_email on any input
model. Both are taken from the authenticated caller in the router, so a client
cannot write into -- or read out of -- another company's data by putting a
different value in the body.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.company_award_models import SOURCE_MANUAL, SOURCE_PDF


class AwardFields(BaseModel):
    """The values a company may supply.

    Every field is optional and None means "not supplied", which is what makes
    the field fall through to the BOSA value rather than blanking it. To clear a
    field a client sends an empty string, which the validator below turns into
    None; there is deliberately no way to force a stored blank.
    """

    title: Optional[str] = None
    award_date: Optional[datetime] = None
    winner: Optional[str] = None
    buyer: Optional[str] = None
    value: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    reference_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("title", "winner", "buyer", "currency", "reference_number", "notes")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class AwardEntryIn(AwardFields):
    """Body for creating or updating an entry."""

    source: str = SOURCE_MANUAL
    source_document_name: Optional[str] = None

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in (SOURCE_MANUAL, SOURCE_PDF):
            raise ValueError(f"source must be one of {SOURCE_MANUAL!r}, {SOURCE_PDF!r}")
        return v


class AwardEntryOut(AwardFields):
    id: int
    publication_workspace_id: Optional[str] = None
    source: str
    source_document_name: Optional[str] = None
    created_by_email: str
    created_at: datetime
    updated_at: datetime

    # Which fields this company actually supplied, so the UI can badge them
    # instead of guessing by comparing against the BOSA row.
    supplied_fields: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ExtractedAward(AwardFields):
    """What the model read out of an uploaded document.

    Nothing here is written anywhere: the endpoint returns it for the user to
    check and correct, and only a subsequent save persists anything. `warnings`
    carries whatever the model could not read confidently, so the UI can point
    at the fields worth a second look rather than implying the whole extraction
    is trustworthy.
    """

    warnings: List[str] = Field(default_factory=list)
    source_document_name: Optional[str] = None
