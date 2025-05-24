from pydantic import BaseModel, EmailStr, HttpUrl, Field
from typing import Optional, List
from datetime import date


class Address(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    nuts_code: Optional[str] = None


class ContactPerson(BaseModel):
    name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class Organization(BaseModel):
    name: str
    business_id: Optional[str] = None
    website: Optional[HttpUrl] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[Address] = None
    contact_persons: Optional[List[ContactPerson]] = []
    company_size: Optional[str] = None
    subcontracting: Optional[str] = None


class Contract(BaseModel):
    notice_id: str
    contract_id: str
    internal_id: Optional[str] = None
    issue_date: Optional[date] = None
    notice_type: Optional[str] = None

    # Financial Information
    total_contract_amount: Optional[float] = None
    currency: Optional[str] = Field(default="EUR", max_length=3)
    lowest_publication_amount: Optional[float] = None
    highest_publication_amount: Optional[float] = None

    # Publication Process Information
    number_of_publications_received: Optional[int] = None
    number_of_participation_requests: Optional[int] = None
    electronic_auction_used: Optional[bool] = None
    dynamic_purchasing_system: Optional[str] = None
    framework_agreement: Optional[str] = None

    # Related Organizations
    contracting_authority: Optional[Organization] = None
    winning_publisher: Optional[Organization] = None
    appeals_body: Optional[Organization] = None
    service_provider: Optional[Organization] = None
