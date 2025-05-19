from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, HttpUrl, validator


class AddressBase(BaseModel):
    """Base model for address information"""
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    nuts_code: Optional[str] = None
    country_code: Optional[str] = None

    class Config:
        from_attributes = True


class AddressCreate(AddressBase):
    """Schema for creating an address"""
    pass


class AddressRead(AddressBase):
    """Schema for reading an address"""
    id: int
    created_at: datetime
    updated_at: datetime


class ContactBase(BaseModel):
    """Base model for contact information"""
    name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    class Config:
        from_attributes = True


class ContactCreate(ContactBase):
    """Schema for creating a contact"""
    pass


class ContactRead(ContactBase):
    """Schema for reading a contact"""
    id: int
    created_at: datetime
    updated_at: datetime


class AppealsBodyContactBase(BaseModel):
    """Base model for appeals body contact information"""
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    class Config:
        from_attributes = True


class AppealsBodyContactCreate(AppealsBodyContactBase):
    """Schema for creating an appeals body contact"""
    pass


class AppealsBodyContactRead(AppealsBodyContactBase):
    """Schema for reading an appeals body contact"""
    id: int
    created_at: datetime
    updated_at: datetime


class AppealsBodyBase(BaseModel):
    """Base model for appeals body information"""
    name: Optional[str] = None
    vat_number: Optional[str] = None
    website: Optional[HttpUrl] = None

    class Config:
        from_attributes = True


class AppealsBodyCreate(AppealsBodyBase):
    """Schema for creating an appeals body"""
    contact: Optional[AppealsBodyContactCreate] = None
    address: Optional[AddressCreate] = None


class AppealsBodyRead(AppealsBodyBase):
    """Schema for reading an appeals body"""
    id: int
    contact: Optional[AppealsBodyContactRead] = None
    address: Optional[AddressRead] = None
    created_at: datetime
    updated_at: datetime


class OrganizationBase(BaseModel):
    """Base model for organization information"""
    name: Optional[str] = None
    vat_number: Optional[str] = None
    website: Optional[HttpUrl] = None

    class Config:
        from_attributes = True


class OrganizationCreate(OrganizationBase):
    """Schema for creating an organization"""
    contact: Optional[ContactCreate] = None
    address: Optional[AddressCreate] = None


class OrganizationRead(OrganizationBase):
    """Schema for reading an organization"""
    id: int
    contact: Optional[ContactRead] = None
    address: Optional[AddressRead] = None
    created_at: datetime
    updated_at: datetime


class WinnerBase(BaseModel):
    """Base model for winning tenderer information"""
    name: Optional[str] = None
    vat_number: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    website: Optional[HttpUrl] = None
    size: Optional[str] = None
    tender_reference: Optional[str] = None
    subcontracting: Optional[str] = None

    # For validating URLs even when they're passed as strings
    @validator('website', pre=True)
    def validate_url(cls, v):
        if v is None:
            return v
        if isinstance(v, str) and not v.startswith(('http://', 'https://')):
            return f'https://{v}'
        return v

    class Config:
        from_attributes = True


class WinnerCreate(WinnerBase):
    """Schema for creating a winner"""
    address: Optional[AddressCreate] = None


class WinnerRead(WinnerBase):
    """Schema for reading a winner"""
    id: int
    address: Optional[AddressRead] = None
    created_at: datetime
    updated_at: datetime


class AwardSupplierBase(BaseModel):
    """Base model for suppliers"""
    name: str
    vat_number: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    website: Optional[HttpUrl] = None

    # For validating URLs even when they're passed as strings
    @validator('website', pre=True)
    def validate_url(cls, v):
        if v is None:
            return v
        if isinstance(v, str) and not v.startswith(('http://', 'https://')):
            return f'https://{v}'
        return v

    class Config:
        from_attributes = True


class AwardSupplierCreate(AwardSupplierBase):
    """Schema for creating a supplier"""
    address: Optional[AddressCreate] = None


class AwardSupplierRead(AwardSupplierBase):
    """Schema for reading a supplier"""
    id: int
    award_id: int
    address: Optional[AddressRead] = None
    created_at: datetime
    updated_at: datetime


class AwardBase(BaseModel):
    """Base model for award information"""
    # Basic Information
    notice_id: Optional[str] = None
    contract_id: Optional[str] = None
    internal_id: Optional[str] = None
    issue_date: Optional[datetime] = None
    notice_type: Optional[str] = None

    # Award values
    award_date: Optional[datetime] = None
    award_value: Optional[float] = None
    lowest_tender_amount: Optional[float] = None
    highest_tender_amount: Optional[float] = None
    currency: Optional[str] = Field(None, max_length=10)

    # Tender process information
    tenders_received: Optional[int] = None
    participation_requests: Optional[int] = None
    electronic_auction_used: Optional[bool] = None
    dynamic_purchasing_system: Optional[str] = None
    framework_agreement: Optional[str] = None

    # Contract details
    contract_reference: Optional[str] = None
    contract_title: Optional[str] = None
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class AwardCreate(AwardBase):
    """Schema for creating an award record"""
    winner: Optional[WinnerCreate] = None
    organization: Optional[OrganizationCreate] = None
    appeals_body: Optional[AppealsBodyCreate] = None
    suppliers: Optional[List[AwardSupplierCreate]] = []
    # XML content for storage
    xml_content: Optional[str] = None


class AwardUpdate(BaseModel):
    """Schema for updating an award record"""
    # Basic Information
    notice_id: Optional[str] = None
    contract_id: Optional[str] = None
    internal_id: Optional[str] = None
    issue_date: Optional[datetime] = None
    notice_type: Optional[str] = None

    # Award values
    award_date: Optional[datetime] = None
    award_value: Optional[float] = None
    lowest_tender_amount: Optional[float] = None
    highest_tender_amount: Optional[float] = None
    currency: Optional[str] = None

    # Tender process information
    tenders_received: Optional[int] = None
    participation_requests: Optional[int] = None
    electronic_auction_used: Optional[bool] = None
    dynamic_purchasing_system: Optional[str] = None
    framework_agreement: Optional[str] = None

    # Contract details
    contract_reference: Optional[str] = None
    contract_title: Optional[str] = None
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None

    # Nested objects (with their own IDs if they exist already)
    winner: Optional[WinnerCreate] = None
    winner_id: Optional[int] = None
    
    organization: Optional[OrganizationCreate] = None
    organization_id: Optional[int] = None
    
    appeals_body: Optional[AppealsBodyCreate] = None
    appeals_body_id: Optional[int] = None
    
    suppliers: Optional[List[AwardSupplierCreate]] = None
    
    # XML content update
    xml_content: Optional[str] = None

    class Config:
        from_attributes = True


class AwardRead(AwardBase):
    """Schema for reading an award record"""
    id: int
    publication_workspace_id: str
    winner: Optional[WinnerRead] = None
    organization: Optional[OrganizationRead] = None
    appeals_body: Optional[AppealsBodyRead] = None
    suppliers: List[AwardSupplierRead] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AwardInDB(AwardRead):
    """Schema with additional database fields"""
    xml_content: Optional[str] = None
    