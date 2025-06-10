import re
from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator
from typing import Dict, Optional, List
from datetime import date, datetime

# TODO: remove all nulls and make all fields required, after you have fixed the db
class ContractAddressSchema(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    nuts_code: Optional[str] = None


class ContractContactPersonSchema(BaseModel):
    name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class ContractOrganizationSchema(BaseModel):
    name: str
    business_id: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[ContractAddressSchema] = None
    contact_persons: Optional[List[ContractContactPersonSchema]] = []
    company_size: Optional[str] = None
    subcontracting: Optional[str] = None

    @field_validator('business_id')
    @classmethod
    def clean_vat_number(cls, v):
        """
        Clean and format VAT number by removing spaces, dots, dashes and other separators.
        Examples:
        - "BE XX.XX" -> "BEXXXX"
        - "BE 1234.567.890" -> "BE1234567890"
        - "FR 12 345 678 901" -> "FR12345678901"
        - "DE123-456-789" -> "DE123456789"
        """
        if not v:
            return v
        
        # Remove all non-alphanumeric characters (spaces, dots, dashes, etc.)
        cleaned = re.sub(r'[^A-Za-z0-9]', '', str(v))
        
        # Convert to uppercase for consistency
        return cleaned.upper() if cleaned else None

class ContractSchema(BaseModel):
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
    contracting_authority: Optional[ContractOrganizationSchema] = None
    winning_publisher: Optional[ContractOrganizationSchema] = None
    appeals_body: Optional[ContractOrganizationSchema] = None
    service_provider: Optional[ContractOrganizationSchema] = None


class AwardSummary(BaseModel):
    """Basic summary of award data"""

    total_value: float = Field(..., description="Total value of awarded contracts")
    total_count: int = Field(..., description="Total number of awarded contracts")
    avg_value: float = Field(..., description="Average value per contract")

    class Config:
        json_schema_extra = {
            "example": {
                "total_value": 5250000.0,
                "total_count": 25,
                "avg_value": 210000.0,
            }
        }


class ContractItem(BaseModel):
    """Data for individual awarded contract"""

    publication_id: str = Field(..., description="Publication workspace ID")
    title: str = Field(..., description="Contract title")
    award_date: Optional[datetime] = Field(None, description="Award date")
    winner: str = Field(..., description="Winner company name")
    suppliers: List[Dict[str, str]] = Field(
        default_factory=list, description="Suppliers involved"
    )
    value: float = Field(..., description="Contract value")
    sector: str = Field(..., description="Main sector")
    cpv_code: str = Field(..., description="Main CPV code")
    buyer: str = Field(..., description="Contracting authority")

    class Config:
        json_schema_extra = {
            "example": {
                "publication_id": "2024-S-001234-5678",
                "title": "Highway maintenance services",
                "award_date": "2024-01-15T00:00:00",
                "winner": "Road Services Ltd",
                "suppliers": [{"name": "Asphalt Inc.", "id": "BE0123456789"}],
                "value": 250000.0,
                "sector": "Maintenance services",
                "cpv_code": "50000000",
                "buyer": "Department of Transportation",
            }
        }
