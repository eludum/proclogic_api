from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page, Params

from app.config.postgres import get_session
from app.crud import award_analytics
from app.crud.publication_contract import get_contracts_summary, get_paginated_contracts
from app.schemas.publication_contract_schemas import AwardSummary, ContractItem
from app.util.publication_utils.contract import (
    convert_publications_to_contract_items,
    format_validation_errors,
    validate_filters,
)
from app.util.clerk import AuthUser, get_auth_user

contracts_router = APIRouter()


@contracts_router.get("/contracts", response_model=Page[ContractItem])
def get_contracts(
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(100, ge=1, le=500, description="Items per page"),
    # Search
    search: Optional[str] = Query(
        None, description="Search in winner, buyer, or supplier names"
    ),
    # Time filters
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(
        None, ge=1, le=4, description="Filter by quarter (1-4)"
    ),
    month: Optional[int] = Query(
        None, ge=1, le=12, description="Filter by month (1-12)"
    ),
    # Entity filters
    sector_code: Optional[str] = Query(
        None, description="Filter by sector CPV code (e.g., '45' for construction)"
    ),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    # Sorting
    sort_by: str = Query(
        "publication_date",
        description="Sort field: publication_date, value, winner, buyer",
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    auth_user: AuthUser = Depends(get_auth_user),
) -> Page[ContractItem]:
    """
    Get paginated list of awarded contracts with search and filtering capabilities.

    This endpoint returns contracts (publications with awards) with comprehensive
    filtering options for analytics purposes.

    **Search**: Searches across winner, buyer, and supplier names.

    **Time Filters**: Filter by year, quarter, and/or month.

    **Entity Filters**: Filter by sector, winner, or supplier.

    **Sorting**: Sort by publication date, contract value, winner name, or buyer name.
    """

    # Validate filters
    validation_errors = validate_filters(
        year=year, quarter=quarter, month=month, page=page, size=size
    )

    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Validation errors: {format_validation_errors(validation_errors)}",
        )

    with get_session() as session:
        # Get paginated publications with contracts
        publications, total_count = get_paginated_contracts(
            session=session,
            page=page,
            size=size,
            search=search,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            winner=winner,
            supplier=supplier,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Convert to ContractItem schemas
        contracts = convert_publications_to_contract_items(publications)

        # Create paginated response
        params = Params(page=page, size=size)
        return Page.create(items=contracts, total=total_count, params=params)


@contracts_router.get("/contracts/summary", response_model=AwardSummary)
def get_contracts_summary_endpoint(
    # Search
    search: Optional[str] = Query(
        None, description="Search in winner, buyer, or supplier names"
    ),
    # Time filters
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(
        None, ge=1, le=4, description="Filter by quarter (1-4)"
    ),
    month: Optional[int] = Query(
        None, ge=1, le=12, description="Filter by month (1-12)"
    ),
    # Entity filters
    sector_code: Optional[str] = Query(None, description="Filter by sector CPV code"),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    auth_user: AuthUser = Depends(get_auth_user),
) -> AwardSummary:
    """
    Get summary statistics for contracts matching the given filters.

    Returns aggregated data: total value, count, and average value for all
    contracts that match the specified filters.

    **Filters**: Uses the same filtering system as the contracts endpoint.
    """

    # Validate filters
    validation_errors = validate_filters(year=year, quarter=quarter, month=month)

    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Validation errors: {format_validation_errors(validation_errors)}",
        )

    with get_session() as session:
        # Get summary statistics
        total_count, total_value, avg_value = get_contracts_summary(
            session=session,
            search=search,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            winner=winner,
            supplier=supplier,
        )

        return AwardSummary(
            total_count=total_count,
            total_value=total_value,
            avg_value=avg_value,
        )


def award_filters(
    search: Optional[str] = Query(
        None, description="Free-text search over title, description, buyer and winner"
    ),
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, ge=1, le=4, description="Filter by quarter"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month"),
    sector_code: Optional[str] = Query(
        None, description="CPV sector, first two digits (e.g. '45')"
    ),
    cpv_code: Optional[str] = Query(
        None, description="CPV code at any precision (e.g. '45233')"
    ),
    region: Optional[List[str]] = Query(
        None, description="NUTS codes; prefixes match descendants"
    ),
    winner: Optional[str] = Query(None, description="Filter by winner name"),
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    buyer: Optional[str] = Query(None, description="Filter by contracting authority"),
    min_value: Optional[float] = Query(None, description="Minimum awarded amount"),
    max_value: Optional[float] = Query(None, description="Maximum awarded amount"),
) -> Dict[str, Any]:
    """Shared filter set for every award breakdown.

    One definition so the breakdowns, the list endpoint and the summary can
    never diverge -- a breakdown filtering differently from the summary would
    silently fail to reconcile.
    """
    return {
        "search": search,
        "year": year,
        "quarter": quarter,
        "month": month,
        "sector_code": sector_code,
        "cpv_code": cpv_code,
        "region": region,
        "winner": winner,
        "supplier": supplier,
        "buyer": buyer,
        "min_value": min_value,
        "max_value": max_value,
    }


@contracts_router.get("/contracts/by-sector")
def get_awards_by_sector(
    filters: Dict[str, Any] = Depends(award_filters),
    limit: int = Query(25, ge=1, le=200),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Award count and value grouped by CPV sector."""
    with get_session() as session:
        return {"sectors": award_analytics.awards_by_sector(session, limit=limit, **filters)}


@contracts_router.get("/contracts/by-region")
def get_awards_by_region(
    filters: Dict[str, Any] = Depends(award_filters),
    limit: int = Query(25, ge=1, le=200),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Award count and value grouped by NUTS region.

    A publication covering several regions is counted in each, so the group
    totals deliberately exceed the overall total.
    """
    with get_session() as session:
        return {"regions": award_analytics.awards_by_region(session, limit=limit, **filters)}


@contracts_router.get("/contracts/by-winner")
def get_awards_by_winner(
    filters: Dict[str, Any] = Depends(award_filters),
    limit: int = Query(25, ge=1, le=200),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Winning companies ranked by total awarded value."""
    with get_session() as session:
        return {"winners": award_analytics.awards_by_winner(session, limit=limit, **filters)}


@contracts_router.get("/contracts/by-supplier")
def get_awards_by_supplier(
    filters: Dict[str, Any] = Depends(award_filters),
    limit: int = Query(25, ge=1, le=200),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Named service providers ranked by total awarded value."""
    with get_session() as session:
        return {"suppliers": award_analytics.awards_by_supplier(session, limit=limit, **filters)}


@contracts_router.get("/contracts/by-buyer")
def get_awards_by_buyer(
    filters: Dict[str, Any] = Depends(award_filters),
    limit: int = Query(25, ge=1, le=200),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Contracting authorities ranked by what they award."""
    with get_session() as session:
        return {"buyers": award_analytics.awards_by_buyer(session, limit=limit, **filters)}


@contracts_router.get("/contracts/timeseries")
def get_awards_timeseries(
    filters: Dict[str, Any] = Depends(award_filters),
    granularity: str = Query("month", pattern="^(month|quarter|year)$"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Award count and value over time."""
    with get_session() as session:
        return {
            "series": award_analytics.awards_timeseries(
                session, granularity=granularity, **filters
            )
        }
