from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CompanyPublicationMatchSchema(BaseModel):
    publication_workspace_id: str
    company_vat_number: str
    match_percentage: float = 0.0
    is_recommended: bool = False
    is_saved: bool = False
    is_viewed: bool = False

    model_config = ConfigDict(from_attributes=True)


class SectorSchema(BaseModel):
    sector: str
    cpv_codes: List[str]

    model_config = ConfigDict(from_attributes=True)


class CompanySchema(BaseModel):
    vat_number: str
    subscription: str = Field(
        default="starter",
        description="Type of subscription: starter, team or custom",
    )
    name: str
    emails: List[str]
    number_of_employees: int = Field(default=1)
    interested_sectors: List[SectorSchema] = Field(default_factory=list)
    summary_activities: str
    accreditations: Optional[dict] = None
    max_publication_value: Optional[int] = None
    activity_keywords: Optional[List[str]] = Field(default_factory=list)
    operating_regions: Optional[List[str]] = Field(default_factory=list)

    # Trial and subscription fields
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    is_trial_active: bool = False
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: str = "inactive"

    publication_matches: Optional[List[CompanyPublicationMatchSchema]] = Field(
        default_factory=list
    )

    model_config = ConfigDict(from_attributes=True)


class SectorUpdateSchema(BaseModel):
    sector: str
    cpv_codes: List[str]


class CompanyUpdateSchema(BaseModel):
    name: Optional[str] = None
    emails: Optional[List[str]] = None
    number_of_employees: Optional[int] = Field(None)
    summary_activities: Optional[str] = None
    interested_sectors: Optional[List[SectorUpdateSchema]] = None
    accreditations: Optional[dict] = None
    max_publication_value: Optional[int] = None
    activity_keywords: Optional[List[str]] = None
    operating_regions: Optional[List[str]] = None

    class Config:
        extra = "ignore"  # Ignore any extra fields


class TrialInviteRequest(BaseModel):
    email: str
    company_name: str
    company_vat_number: str
    summary_activities: str = ""


class SubscriptionStatusResponse(BaseModel):
    has_access: bool
    subscription_status: str
    trial_days_remaining: Optional[int] = None
    trial_end_date: Optional[datetime] = None
    message: str
