from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, extract, func

from app.config.postgres import get_session
from app.models.publication_models import CPVCode, Publication
from app.util.clerk import AuthUser, get_auth_user
from app.util.publication_utils.cpv_codes import (
    get_cpv_sector_code,
    get_cpv_sector_name,
)
from app.util.publication_utils.nuts_codes import get_nuts_code_as_str
from app.util.publication_utils.publication_converter import PublicationConverter

analytics_router = APIRouter()

# TODO: add documents to publication

# ----- Pydantic Models for Response Data -----


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


# ----- Utility Functions -----


def get_time_period_filter(
    year: Optional[int], quarter: Optional[int], month: Optional[int]
):
    """Generate a SQLAlchemy filter based on time period parameters"""
    conditions = []

    if year:
        conditions.append(extract("year", Publication.publication_date) == year)

    if quarter:
        conditions.append(extract("quarter", Publication.publication_date) == quarter)

    if month:
        conditions.append(extract("month", Publication.publication_date) == month)

    return and_(*conditions) if conditions else None


def get_sector_filter(sector_code: Optional[str] = None):
    """Generate a SQLAlchemy filter for CPV sector"""
    if not sector_code:
        return None

    # If only the first two digits are provided (sector level)
    if len(sector_code) == 2:
        return func.substring(CPVCode.code, 1, 2) == sector_code

    # For complete CPV codes
    return CPVCode.code == sector_code


def format_time_period(period_type: str, date_value: date) -> str:
    """Format a date into a consistent period string based on period type"""
    year = date_value.year

    if period_type == "yearly":
        return str(year)
    elif period_type == "quarterly":
        quarter = (date_value.month - 1) // 3 + 1
        return f"{year}-Q{quarter}"
    else:  # monthly
        return f"{year}-{date_value.month:02d}"


def organize_by_time_period(
    data: List[Dict], period_type: str = "monthly"
) -> List[AwardTimeSeriesItem]:
    """Organize award data into time periods"""
    periods = {}

    for item in data:
        date_value = item.get("date")
        if not date_value:
            continue

        period_key = format_time_period(period_type, date_value)

        if period_key not in periods:
            periods[period_key] = {"period": period_key, "count": 0, "total_value": 0}

        periods[period_key]["count"] += 1
        periods[period_key]["total_value"] += item.get("value", 0)

    # Convert to list and sort
    result = [AwardTimeSeriesItem(**p) for p in periods.values()]

    # Sort based on period type
    if period_type == "yearly":
        result.sort(key=lambda x: x.period)
    elif period_type == "quarterly":
        result.sort(key=lambda x: (x.period.split("-")[0], x.period.split("-")[1]))
    else:  # monthly
        result.sort(key=lambda x: x.period)

    return result


def get_award_value(pub: Publication) -> float:
    """Extract the award value from a publication"""
    if not pub.award:
        return 0

    return pub.award.get("value", 0)


def get_publication_title(pub: Publication) -> str:
    """Get publication title from dossier titles"""
    if pub.dossier and pub.dossier.titles:
        return PublicationConverter.get_descr_as_str(pub.dossier.titles)
    return "Untitled"


def get_buyer_name(pub: Publication) -> str:
    """Get the buyer (contracting authority) name"""
    if pub.organisation and pub.organisation.organisation_names:
        return PublicationConverter.get_org_name_as_str(
            pub.organisation.organisation_names
        )
    return "Unknown Buyer"


def get_suppliers_from_award(pub: Publication) -> List[Dict[str, str]]:
    """Extract suppliers from publication award data"""
    if not pub.award:
        return []

    # Some awards might have suppliers directly
    if "suppliers" in pub.award and isinstance(pub.award["suppliers"], list):
        return pub.award.get("suppliers", [])

    # Handle case where suppliers is a string or doesn't exist
    return []


# ----- Endpoint Implementations -----


@analytics_router.get("/awards/summary", response_model=AwardSummary)
async def get_awards_summary(
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    month: Optional[int] = Query(None, description="Filter by month (1-12)"),
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get summary statistics about awarded contracts.

    This endpoint provides aggregate information about awarded contracts, including total value,
    count, and average value. You can filter by time period, sector, winner, or supplier.
    """
    with get_session() as session:
        query = session.query(Publication).filter(Publication.award.isnot(None))

        # Apply time period filter
        time_filter = get_time_period_filter(year, quarter, month)
        if time_filter:
            query = query.filter(time_filter)

        # Apply sector filter
        if sector_code:
            sector_filter = get_sector_filter(sector_code)
            if sector_filter:
                query = query.join(Publication.cpv_main_code).filter(sector_filter)

        # Apply winner filter
        if winner:
            query = query.filter(
                Publication.award["winner"].astext.ilike(f"%{winner}%")
            )

        # Apply supplier filter
        if supplier:
            query = query.filter(
                Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
            )

        publications = query.all()

        # Calculate statistics
        count = len(publications)
        total_value = sum(get_award_value(pub) for pub in publications)
        avg_value = total_value / count if count > 0 else 0

        return AwardSummary(
            total_value=total_value, total_count=count, avg_value=avg_value
        )


@analytics_router.get("/awards/timeseries", response_model=List[AwardTimeSeriesItem])
async def get_awards_timeseries(
    period_type: str = Query(
        "monthly", description="Time grouping: monthly, quarterly, or yearly"
    ),
    year: Optional[int] = Query(None, description="Filter by year"),
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get time series data for awarded contracts.

    This endpoint provides award data grouped by time periods. You can specify the period type
    (monthly, quarterly, yearly) and filter by year, sector, winner, or supplier.
    """
    with get_session() as session:
        # Base query to get all awarded publications with required data
        query = session.query(Publication).filter(Publication.award.isnot(None))

        # Apply year filter if provided
        if year:
            query = query.filter(extract("year", Publication.publication_date) == year)

        # Apply sector filter if provided
        if sector_code:
            sector_filter = get_sector_filter(sector_code)
            if sector_filter:
                query = query.join(Publication.cpv_main_code).filter(sector_filter)

        # Apply winner filter if provided
        if winner:
            query = query.filter(
                Publication.award["winner"].astext.ilike(f"%{winner}%")
            )

        # Apply supplier filter if provided
        if supplier:
            query = query.filter(
                Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
            )

        publications = query.all()

        # Convert to dictionaries for processing
        data = [
            {"date": pub.publication_date, "value": get_award_value(pub)}
            for pub in publications
        ]

        # Organize by time period
        return organize_by_time_period(data, period_type)


@analytics_router.get("/awards/by-sector", response_model=List[AwardSectorItem])
async def get_awards_by_sector(
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    month: Optional[int] = Query(None, description="Filter by month (1-12)"),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    language: str = Query("nl", description="Language for sector names (nl, en, fr)"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get awarded contracts grouped by sector.

    This endpoint provides data about awards grouped by CPV sectors. You can filter by
    time period, winner, and supplier.
    """
    with get_session() as session:
        # Base query to get all awarded publications
        query = session.query(Publication).filter(Publication.award.isnot(None))

        # Apply time period filter
        time_filter = get_time_period_filter(year, quarter, month)
        if time_filter:
            query = query.filter(time_filter)

        # Apply winner filter
        if winner:
            query = query.filter(
                Publication.award["winner"].astext.ilike(f"%{winner}%")
            )

        # Apply supplier filter
        if supplier:
            query = query.filter(
                Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
            )

        publications = query.all()

        # Process results into sector data
        sector_totals = {}  # For aggregating to sector level

        for pub in publications:
            # Get sector code (first two digits + zeros)
            sector_code = get_cpv_sector_code(pub.cpv_main_code.code)

            # If we don't have this sector yet, add it
            if sector_code not in sector_totals:
                sector_name = get_cpv_sector_name(sector_code, language)
                sector_totals[sector_code] = {
                    "sector": sector_name,
                    "sector_code": sector_code,
                    "count": 0,
                    "total_value": 0,
                }

            # Add this publication's data to the sector total
            sector_totals[sector_code]["count"] += 1
            sector_totals[sector_code]["total_value"] += get_award_value(pub)

        # Convert to response items
        sectors = [AwardSectorItem(**data) for data in sector_totals.values()]

        # Sort by total value
        sectors.sort(key=lambda x: x.total_value, reverse=True)

        return sectors


@analytics_router.get("/awards/by-region", response_model=List[RegionItem])
async def get_awards_by_region(
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    month: Optional[int] = Query(None, description="Filter by month (1-12)"),
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get award counts and values grouped by geographic regions.

    This endpoint provides data about awards grouped by NUTS regions. You can filter by
    time period, sector, winner, and supplier.
    """
    with get_session() as session:
        # Base query to get all awarded publications
        query = session.query(Publication).filter(Publication.award.isnot(None))

        # Apply time period filter
        time_filter = get_time_period_filter(year, quarter, month)
        if time_filter:
            query = query.filter(time_filter)

        # Apply sector filter
        if sector_code:
            sector_filter = get_sector_filter(sector_code)
            if sector_filter:
                query = query.join(Publication.cpv_main_code).filter(sector_filter)

        # Apply winner filter
        if winner:
            query = query.filter(
                Publication.award["winner"].astext.ilike(f"%{winner}%")
            )

        # Apply supplier filter
        if supplier:
            query = query.filter(
                Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
            )

        publications = query.all()

        # Process data to group by region
        regions = {}
        for pub in publications:
            # A publication can have multiple NUTS codes
            for nuts_code in pub.nuts_codes:
                if not nuts_code:
                    continue

                # Try to get region name
                region_name = get_nuts_code_as_str(nuts_code)
                if not region_name:
                    region_name = f"Region {nuts_code}"  # Fallback if not found

                if nuts_code not in regions:
                    regions[nuts_code] = {
                        "region_code": nuts_code,
                        "region_name": region_name,
                        "count": 0,
                        "total_value": 0,
                    }

                regions[nuts_code]["count"] += 1
                regions[nuts_code]["total_value"] += get_award_value(pub)

        # Convert to list and sort by total value
        result = [RegionItem(**r) for r in regions.values()]
        result.sort(key=lambda x: x.total_value, reverse=True)

        return result


@analytics_router.get("/awards/by-winner", response_model=List[WinnerItem])
async def get_awards_by_winner(
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    month: Optional[int] = Query(None, description="Filter by month (1-12)"),
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    limit: int = Query(20, description="Limit number of winners returned"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get awarded contracts grouped by winner.

    This endpoint provides data about which companies have won contracts, including the
    number of contracts and total value. You can filter by time period and sector.
    """
    with get_session() as session:
        # Base query to get all awarded publications
        query = session.query(Publication).filter(Publication.award.isnot(None))

        # Apply time period filter
        time_filter = get_time_period_filter(year, quarter, month)
        if time_filter:
            query = query.filter(time_filter)

        # Apply sector filter
        if sector_code:
            sector_filter = get_sector_filter(sector_code)
            if sector_filter:
                query = query.join(Publication.cpv_main_code).filter(sector_filter)

        publications = query.all()

        # Process data to group by winner
        winners = {}
        for pub in publications:
            winner_name = pub.award.get("winner", "Unknown")

            if winner_name not in winners:
                winners[winner_name] = {"count": 0, "total_value": 0, "sectors": set()}

            winners[winner_name]["count"] += 1
            winners[winner_name]["total_value"] += get_award_value(pub)

            # Add sector information
            sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
            sector_name = get_cpv_sector_name(sector_code, "nl")
            winners[winner_name]["sectors"].add(sector_name)

        # Convert to response format
        result = [
            WinnerItem(
                winner=name,
                count=data["count"],
                total_value=data["total_value"],
                sectors=list(data["sectors"]),
            )
            for name, data in winners.items()
        ]

        # Sort by total value and limit
        result.sort(key=lambda x: x.total_value, reverse=True)
        return result[:limit]


@analytics_router.get("/awards/by-supplier", response_model=List[SupplierItem])
async def get_awards_by_supplier(
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    month: Optional[int] = Query(None, description="Filter by month (1-12)"),
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    limit: int = Query(20, description="Limit number of suppliers returned"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get awarded contracts grouped by supplier.

    This endpoint provides data about suppliers involved in contracts, including the
    number of contracts and total value. You can filter by time period and sector.
    """
    with get_session() as session:
        # Base query to get all awarded publications
        query = session.query(Publication).filter(Publication.award.isnot(None))

        # Apply time period filter
        time_filter = get_time_period_filter(year, quarter, month)
        if time_filter:
            query = query.filter(time_filter)

        # Apply sector filter
        if sector_code:
            sector_filter = get_sector_filter(sector_code)
            if sector_filter:
                query = query.join(Publication.cpv_main_code).filter(sector_filter)

        publications = query.all()

        # Process data to group by supplier
        suppliers = {}
        for pub in publications:
            # Get suppliers from award data
            supplier_list = get_suppliers_from_award(pub)

            for supplier_data in supplier_list:
                supplier_name = supplier_data.get("name", "Unknown")
                supplier_id = supplier_data.get("id", None)

                # Create a unique key to avoid duplicates
                key = f"{supplier_name}_{supplier_id}" if supplier_id else supplier_name

                if key not in suppliers:
                    suppliers[key] = {
                        "supplier_name": supplier_name,
                        "supplier_id": supplier_id,
                        "count": 0,
                        "total_value": 0,
                        "sectors": set(),
                    }

                suppliers[key]["count"] += 1
                suppliers[key]["total_value"] += get_award_value(pub)

                # Add sector information
                sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
                sector_name = get_cpv_sector_name(sector_code, "nl")
                suppliers[key]["sectors"].add(sector_name)

        # Convert to response format
        result = [
            SupplierItem(
                supplier_name=data["supplier_name"],
                supplier_id=data["supplier_id"],
                count=data["count"],
                total_value=data["total_value"],
                sectors=list(data["sectors"]),
            )
            for data in suppliers.values()
        ]

        # Sort by total value and limit
        result.sort(key=lambda x: x.total_value, reverse=True)
        return result[:limit]


@analytics_router.get(
    "/awards/winner/{winner_name}", response_model=WinnerDetailResponse
)
async def get_winner_detail(
    winner_name: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    period_type: str = Query(
        "monthly", description="Time grouping: monthly, quarterly, or yearly"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get detailed information about a specific winner.

    This endpoint provides comprehensive data about a specific winning company,
    including summary statistics, time series data, sectors they operate in, and
    a list of contracts they've won.
    """
    with get_session() as session:
        # Get all publications awarded to this winner
        query = session.query(Publication).filter(
            Publication.award.isnot(None),
            Publication.award["winner"].astext.ilike(f"%{winner_name}%"),
        )

        # Apply year filter if provided
        if year:
            query = query.filter(extract("year", Publication.publication_date) == year)

        publications = query.all()

        if not publications:
            raise HTTPException(
                status_code=404, detail=f"No awards found for winner: {winner_name}"
            )

        # Calculate summary statistics
        total_value = sum(get_award_value(pub) for pub in publications)
        count = len(publications)
        avg_value = total_value / count if count > 0 else 0

        # Prepare data for time series
        time_data = [
            {"date": pub.publication_date, "value": get_award_value(pub)}
            for pub in publications
        ]

        # Group by sectors
        sectors = {}
        for pub in publications:
            sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
            sector_name = get_cpv_sector_name(sector_code, "nl")

            if sector_code not in sectors:
                sectors[sector_code] = {
                    "sector": sector_name,
                    "sector_code": sector_code,
                    "count": 0,
                    "total_value": 0,
                }

            sectors[sector_code]["count"] += 1
            sectors[sector_code]["total_value"] += get_award_value(pub)

        # Prepare contract items
        contracts = [
            ContractItem(
                publication_id=pub.publication_workspace_id,
                title=get_publication_title(pub),
                award_date=pub.publication_date,
                winner=pub.award.get("winner", "Unknown"),
                suppliers=get_suppliers_from_award(pub) or [],
                value=get_award_value(pub),
                sector=get_cpv_sector_name(
                    get_cpv_sector_code(pub.cpv_main_code.code), "nl"
                ),
                cpv_code=pub.cpv_main_code.code,
                buyer=get_buyer_name(pub),
            )
            for pub in publications
        ]

        return WinnerDetailResponse(
            winner=winner_name,
            summary=AwardSummary(
                total_value=total_value, total_count=count, avg_value=avg_value
            ),
            time_series=organize_by_time_period(time_data, period_type),
            sectors=[AwardSectorItem(**s) for s in sectors.values()],
            contracts=contracts,
        )


@analytics_router.get(
    "/awards/supplier/{supplier_name}", response_model=SupplierDetailResponse
)
async def get_supplier_detail(
    supplier_name: str,
    supplier_id: Optional[str] = Query(
        None, description="Supplier ID for more specific matching"
    ),
    year: Optional[int] = Query(None, description="Filter by year"),
    period_type: str = Query(
        "monthly", description="Time grouping: monthly, quarterly, or yearly"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get detailed information about a specific supplier.

    This endpoint provides comprehensive data about a specific supplier company,
    including summary statistics, time series data, sectors they operate in, and
    a list of contracts they've been involved in.
    """
    with get_session() as session:
        # Get all publications where this supplier is involved
        query = session.query(Publication).filter(
            Publication.award.isnot(None),
            Publication.award["suppliers"].astext.ilike(f"%{supplier_name}%"),
        )

        # Apply year filter if provided
        if year:
            query = query.filter(extract("year", Publication.publication_date) == year)

        publications = query.all()

        # Filter to ensure the supplier is actually in the list
        filtered_publications = []
        for pub in publications:
            suppliers = get_suppliers_from_award(pub)
            for supplier in suppliers:
                # Check if this is the supplier we're looking for
                if supplier_name.lower() in supplier.get("name", "").lower():
                    # If supplier_id is provided, match that too
                    if supplier_id:
                        if supplier.get("id") == supplier_id:
                            filtered_publications.append(pub)
                            break
                    else:
                        filtered_publications.append(pub)
                        break

        publications = filtered_publications

        if not publications:
            raise HTTPException(
                status_code=404, detail=f"No awards found for supplier: {supplier_name}"
            )

        # Get the most specific supplier ID if available
        specific_supplier_id = None
        for pub in publications:
            suppliers = get_suppliers_from_award(pub)
            for supplier in suppliers:
                if supplier_name.lower() in supplier.get(
                    "name", ""
                ).lower() and supplier.get("id"):
                    specific_supplier_id = supplier.get("id")
                    break
            if specific_supplier_id:
                break

        # Calculate summary statistics
        total_value = sum(get_award_value(pub) for pub in publications)
        count = len(publications)
        avg_value = total_value / count if count > 0 else 0

        # Prepare data for time series
        time_data = [
            {"date": pub.publication_date, "value": get_award_value(pub)}
            for pub in publications
        ]

        # Group by sectors
        sectors = {}
        for pub in publications:
            sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
            sector_name = get_cpv_sector_name(sector_code, "nl")

            if sector_code not in sectors:
                sectors[sector_code] = {
                    "sector": sector_name,
                    "sector_code": sector_code,
                    "count": 0,
                    "total_value": 0,
                }

            sectors[sector_code]["count"] += 1
            sectors[sector_code]["total_value"] += get_award_value(pub)

        # Prepare contract items
        contracts = [
            ContractItem(
                publication_id=pub.publication_workspace_id,
                title=get_publication_title(pub),
                award_date=pub.publication_date,
                winner=pub.award.get("winner", "Unknown"),
                suppliers=get_suppliers_from_award(pub) or [],
                value=get_award_value(pub),
                sector=get_cpv_sector_name(
                    get_cpv_sector_code(pub.cpv_main_code.code), "nl"
                ),
                cpv_code=pub.cpv_main_code.code,
                buyer=get_buyer_name(pub),
            )
            for pub in publications
        ]

        return SupplierDetailResponse(
            supplier_name=supplier_name,
            supplier_id=specific_supplier_id or supplier_id,
            summary=AwardSummary(
                total_value=total_value, total_count=count, avg_value=avg_value
            ),
            time_series=organize_by_time_period(time_data, period_type),
            sectors=[AwardSectorItem(**s) for s in sectors.values()],
            contracts=contracts,
        )
