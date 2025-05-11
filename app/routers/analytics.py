from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config.postgres import get_session
from app.crud import analytics as crud_analytics
from app.schemas.analytics_schemas import (
    AwardSummary,
    AwardTimeSeriesItem,
    AwardSectorItem,
    RegionItem,
    WinnerItem,
    SupplierItem,
    ContractItem,
    WinnerDetailResponse,
    SupplierDetailResponse,
)
from app.crud.analytics_mapper import (
    map_awards_summary,
    map_timeseries_data,
    map_sector_data,
    map_region_data,
    map_winner_data,
    map_supplier_data,
    map_contract_data,
    map_winner_detail,
    map_supplier_detail,
)
from app.util.clerk import AuthUser, get_auth_user

analytics_router = APIRouter()


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
        summary_data = crud_analytics.get_awards_summary(
            session=session,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            winner=winner,
            supplier=supplier,
        )

        return map_awards_summary(summary_data)


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
        time_data = crud_analytics.get_awards_timeseries(
            session=session,
            period_type=period_type,
            year=year,
            sector_code=sector_code,
            winner=winner,
            supplier=supplier,
        )

        return map_timeseries_data(time_data, period_type)


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
        publications = crud_analytics.get_awards_by_sector(
            session=session,
            year=year,
            quarter=quarter,
            month=month,
            winner=winner,
            supplier=supplier,
        )

        return map_sector_data(publications, language)


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
        publications = crud_analytics.get_awards_by_region(
            session=session,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            winner=winner,
            supplier=supplier,
        )

        return map_region_data(publications)


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
        publications = crud_analytics.get_awards_by_winner(
            session=session,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            limit=limit,
        )

        return map_winner_data(publications, limit)


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
        publications = crud_analytics.get_awards_by_supplier(
            session=session,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            limit=limit,
        )

        return map_supplier_data(publications, limit)


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
        publications = crud_analytics.get_winner_detail(
            session=session, winner_name=winner_name, year=year
        )

        if not publications:
            raise HTTPException(
                status_code=404, detail=f"No awards found for winner: {winner_name}"
            )

        return map_winner_detail(publications, winner_name, period_type)


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
        publications = crud_analytics.get_supplier_detail(
            session=session,
            supplier_name=supplier_name,
            supplier_id=supplier_id,
            year=year,
        )

        # Filter to ensure the supplier is actually in the list
        filtered_publications = []
        for pub in publications:
            suppliers = map_supplier_data.get_suppliers_from_award(pub)
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

        if not filtered_publications:
            raise HTTPException(
                status_code=404, detail=f"No awards found for supplier: {supplier_name}"
            )

        return map_supplier_detail(
            filtered_publications, supplier_name, supplier_id, period_type
        )


@analytics_router.get("/awards/contracts", response_model=List[ContractItem])
async def get_contracts(
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    month: Optional[int] = Query(None, description="Filter by month (1-12)"),
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """
    Get a list of awarded contracts with flexible filtering options.
    """
    with get_session() as session:
        publications = crud_analytics.get_contracts(
            session=session,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            winner=winner,
            supplier=supplier,
        )

        return map_contract_data(publications)
