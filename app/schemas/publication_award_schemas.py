from pydantic import BaseModel, EmailStr, HttpUrl, Field
from typing import Dict, Optional, List
from datetime import date, datetime


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
    website: Optional[HttpUrl] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[ContractAddressSchema] = None
    contact_persons: Optional[List[ContractContactPersonSchema]] = []
    company_size: Optional[str] = None
    subcontracting: Optional[str] = None


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


class AwardTimeSeriesItem(BaseModel):
    """Data point for time series analysis"""

    period: str = Field(..., description="Time period (month/quarter/year)")
    count: int = Field(..., description="Number of awards in this period")
    total_value: float = Field(..., description="Total value in this period")

    class Config:
        json_schema_extra = {
            "example": {"period": "2024-01", "count": 5, "total_value": 1250000.0}
        }


class AwardSectorItem(BaseModel):
    """Data for sector analysis"""

    sector: str = Field(..., description="Sector name")
    sector_code: str = Field(..., description="CPV sector code")
    count: int = Field(..., description="Number of awards in this sector")
    total_value: float = Field(..., description="Total value in this sector")

    class Config:
        json_schema_extra = {
            "example": {
                "sector": "Construction work",
                "sector_code": "45000000",
                "count": 7,
                "total_value": 2500000.0,
            }
        }


class RegionItem(BaseModel):
    """Data for regional analysis"""

    region_code: str = Field(..., description="NUTS code for the region")
    region_name: str = Field(..., description="Name of the region")
    count: int = Field(..., description="Number of awards in this region")
    total_value: float = Field(..., description="Total value in this region")

    class Config:
        json_schema_extra = {
            "example": {
                "region_code": "BE1",
                "region_name": "Région de Bruxelles-Capitale/Brussels Hoofdstedelijk Gewest",
                "count": 15,
                "total_value": 4750000.0,
            }
        }


class WinnerItem(BaseModel):
    """Data for winner analysis"""

    winner: str = Field(..., description="Winner company name")
    count: int = Field(..., description="Number of awards won")
    total_value: float = Field(..., description="Total value won")
    sectors: List[str] = Field(
        default_factory=list, description="Sectors the winner operates in"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "winner": "ABC Construction",
                "count": 3,
                "total_value": 750000.0,
                "sectors": ["Construction work", "Architectural services"],
            }
        }


class SupplierItem(BaseModel):
    """Data for supplier analysis"""

    supplier_name: str = Field(..., description="Supplier company name")
    supplier_id: Optional[str] = Field(None, description="Supplier ID (if available)")
    count: int = Field(..., description="Number of awards involved in")
    total_value: float = Field(..., description="Total value of awards involved in")
    sectors: List[str] = Field(
        default_factory=list, description="Sectors the supplier operates in"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "supplier_name": "ABC Construction",
                "supplier_id": "BE0123456789",
                "count": 3,
                "total_value": 750000.0,
                "sectors": ["Construction work", "Architectural services"],
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


class WinnerDetailResponse(BaseModel):
    """Detailed response for a specific winner"""

    winner: str = Field(..., description="Winner name")
    summary: AwardSummary
    time_series: List[AwardTimeSeriesItem] = Field(default_factory=list)
    sectors: List[AwardSectorItem] = Field(default_factory=list)
    contracts: List[ContractItem] = Field(default_factory=list)


class SupplierDetailResponse(BaseModel):
    """Detailed response for a specific supplier"""

    supplier_name: str = Field(..., description="Supplier name")
    supplier_id: Optional[str] = Field(None, description="Supplier ID (if available)")
    summary: AwardSummary
    time_series: List[AwardTimeSeriesItem] = Field(default_factory=list)
    sectors: List[AwardSectorItem] = Field(default_factory=list)
    contracts: List[ContractItem] = Field(default_factory=list)


class SectorDetailResponse(BaseModel):
    """Detailed response for a specific sector"""

    sector: str = Field(..., description="Sector name")
    sector_code: str = Field(..., description="Sector CPV code")
    summary: AwardSummary
    time_series: List[AwardTimeSeriesItem] = Field(default_factory=list)
    winners: List[WinnerItem] = Field(default_factory=list)
    suppliers: List[SupplierItem] = Field(default_factory=list)
    contracts: List[ContractItem] = Field(default_factory=list)
