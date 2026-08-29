import logging
from typing import List, Optional, Tuple

from sqlalchemy import and_, extract, func, or_
from sqlalchemy.orm import Session, joinedload

from app.crud.fts import (
    build_fts_condition,
    build_fts_rank,
    build_region_condition,
    build_value_condition,
)
from app.models.publication_contract_models import Contract, ContractOrganization
from app.models.publication_models import Dossier, Publication


def build_search_filter(search_term: str):
    """Build search filter for contract publications.

    Matches the flattened Dutch full-text blob (title, description, lots, buyer,
    winner) as well as the organisation names directly. The organisation arms
    are kept alongside the full-text one because searchable_content is populated
    at ingest and may still be NULL on rows that predate the backfill -- without
    them, an un-backfilled award would be invisible to search.
    """
    if not search_term or not search_term.strip():
        return None

    search_pattern = f"%{search_term.strip()}%"

    conditions = [
        # Search in winner name (through contract -> winning_publisher)
        Publication.contract.has(
            Contract.winning_publisher.has(
                func.lower(ContractOrganization.name).like(func.lower(search_pattern))
            )
        ),
        # Search in buyer name (through contract -> contracting_authority)
        Publication.contract.has(
            Contract.contracting_authority.has(
                func.lower(ContractOrganization.name).like(func.lower(search_pattern))
            )
        ),
        # Search in service provider name
        Publication.contract.has(
            Contract.service_provider.has(
                func.lower(ContractOrganization.name).like(func.lower(search_pattern))
            )
        ),
        Publication.contract.has(
            Contract.winning_publisher.has(
                func.lower(ContractOrganization.business_id).like(
                    func.lower(search_pattern)
                )
            )
        ),
    ]

    fts_condition = build_fts_condition(search_term)
    if fts_condition is not None:
        conditions.append(fts_condition)

    return or_(*conditions)


def build_time_filter(
    year: Optional[int], quarter: Optional[int], month: Optional[int]
):
    """Build time period filter"""
    conditions = []

    if year:
        conditions.append(extract("year", Publication.publication_date) == year)

    if quarter:
        conditions.append(extract("quarter", Publication.publication_date) == quarter)

    if month:
        conditions.append(extract("month", Publication.publication_date) == month)

    return and_(*conditions) if conditions else None


def build_sector_filter(sector_code: Optional[str]):
    """Build sector filter based on CPV code"""
    if not sector_code:
        return None

    # Handle sector-level filtering (first 2 digits)
    if len(sector_code) >= 2:
        sector_prefix = sector_code[:2]
        return Publication.cpv_main_code_code.like(f"{sector_prefix}%")

    return None


def build_cpv_filter(cpv_code: Optional[str]):
    """Build a CPV filter at whatever precision the caller supplied.

    Distinct from build_sector_filter, which always truncates to two digits:
    passing "45233120" here means that exact kind of work, not all construction.
    """
    if not cpv_code or not cpv_code.strip():
        return None

    prefix = cpv_code.strip().rstrip("-0") or cpv_code.strip()
    return Publication.cpv_main_code_code.like(f"{prefix}%")


def build_winner_filter(winner: Optional[str]):
    """Build winner filter"""
    if not winner or not winner.strip():
        return None

    winner_pattern = f"%{winner.strip()}%"
    return Publication.contract.has(
        Contract.winning_publisher.has(
            func.lower(ContractOrganization.name).like(func.lower(winner_pattern))
        )
    )


def build_supplier_filter(supplier: Optional[str]):
    """Build supplier filter"""
    if not supplier or not supplier.strip():
        return None

    supplier_pattern = f"%{supplier.strip()}%"
    return Publication.contract.has(
        Contract.service_provider.has(
            func.lower(ContractOrganization.name).like(func.lower(supplier_pattern))
        )
    )


def build_buyer_filter(buyer: Optional[str]):
    """Build contracting-authority filter"""
    if not buyer or not buyer.strip():
        return None

    buyer_pattern = f"%{buyer.strip()}%"
    return Publication.contract.has(
        Contract.contracting_authority.has(
            func.lower(ContractOrganization.name).like(func.lower(buyer_pattern))
        )
    )


def build_contract_value_filter(
    min_value: Optional[float], max_value: Optional[float]
):
    """Bound the awarded amount. Rows with no published amount are excluded."""
    if min_value is None and max_value is None:
        return None

    condition = build_value_condition(
        min_value, max_value, Contract.total_contract_amount
    )
    if condition is None:
        return None

    return Publication.contract.has(condition)


def apply_contract_filters(
    query,
    search: Optional[str] = None,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    cpv_code: Optional[str] = None,
    region: Optional[List[str]] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
    buyer: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
):
    """Apply every award filter to a query.

    Single place where the filter set is assembled, so the list endpoint, the
    summary aggregate and all the analytics breakdowns can never drift apart --
    a breakdown that filtered differently from the summary would silently fail
    to reconcile.
    """
    for condition in (
        build_search_filter(search),
        build_time_filter(year, quarter, month),
        build_sector_filter(sector_code),
        build_cpv_filter(cpv_code),
        build_region_condition(region),
        build_winner_filter(winner),
        build_supplier_filter(supplier),
        build_buyer_filter(buyer),
        build_contract_value_filter(min_value, max_value),
    ):
        if condition is not None:
            query = query.filter(condition)

    return query


def get_paginated_contracts(
    session: Session,
    page: int = 1,
    size: int = 100,
    search: Optional[str] = None,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    cpv_code: Optional[str] = None,
    region: Optional[List[str]] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
    buyer: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    sort_by: str = "publication_date",
    sort_order: str = "desc",
) -> Tuple[List[Publication], int]:
    """
    Get paginated list of contract publications with filtering and sorting.

    Returns:
        Tuple[List[Publication], int]: Publications for current page and total count
    """
    try:

        # Base query: only publications with contracts (awards)
        query = session.query(Publication).filter(Publication.contract_id.isnot(None))

        query = apply_contract_filters(
            query,
            search=search,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            cpv_code=cpv_code,
            region=region,
            winner=winner,
            supplier=supplier,
            buyer=buyer,
            min_value=min_value,
            max_value=max_value,
        )

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting with proper joins
        if sort_by == "relevance":
            # Only meaningful with a search term; fall back to recency otherwise
            # so "relevance" is always a safe thing for a tool caller to ask for.
            rank = build_fts_rank(search)
            if rank is not None:
                query = query.order_by(rank.desc(), Publication.publication_date.desc())
            else:
                query = query.order_by(Publication.publication_date.desc())
        elif sort_by == "value":
            query = query.join(
                Contract, Publication.contract_id == Contract.contract_id
            )
            if sort_order.lower() == "desc":
                query = query.order_by(Contract.total_contract_amount.desc())
            else:
                query = query.order_by(Contract.total_contract_amount.asc())
        elif sort_by == "winner":
            query = query.join(
                Contract, Publication.contract_id == Contract.contract_id
            ).join(
                ContractOrganization,
                Contract.winning_publisher_id == ContractOrganization.id,
            )
            if sort_order.lower() == "desc":
                query = query.order_by(ContractOrganization.name.desc())
            else:
                query = query.order_by(ContractOrganization.name.asc())
        elif sort_by == "buyer":
            query = query.join(
                Contract, Publication.contract_id == Contract.contract_id
            ).join(
                ContractOrganization,
                Contract.contracting_authority_id == ContractOrganization.id,
            )
            if sort_order.lower() == "desc":
                query = query.order_by(ContractOrganization.name.desc())
            else:
                query = query.order_by(ContractOrganization.name.asc())
        else:  # default to publication_date
            if sort_order.lower() == "desc":
                query = query.order_by(Publication.publication_date.desc())
            else:
                query = query.order_by(Publication.publication_date.asc())

        # Apply pagination with optimized eager loading to prevent N+1 queries
        # Use subqueryload for collections to avoid cartesian products
        publications = (
            query.options(
                # Load dossier and its nested relationships
                joinedload(Publication.dossier).subqueryload(Dossier.titles),
                joinedload(Publication.dossier).subqueryload(Dossier.descriptions),
                # Load organisation
                joinedload(Publication.organisation),
                # Load CPV code
                joinedload(Publication.cpv_main_code),
                # Load contract with organizations
                joinedload(Publication.contract).joinedload(Contract.winning_publisher),
                joinedload(Publication.contract).joinedload(Contract.contracting_authority),
                joinedload(Publication.contract).joinedload(Contract.service_provider),
            )
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        return publications, total_count

    except Exception as e:
        logging.error(f"Error getting paginated contracts: {e}")
        return [], 0


def get_contracts_summary(
    session: Session,
    search: Optional[str] = None,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    cpv_code: Optional[str] = None,
    region: Optional[List[str]] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
    buyer: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Tuple[int, float, float]:
    """
    Get summary statistics for contracts matching the given filters.

    Returns:
        Tuple[int, float, float]: (total_count, total_value, avg_value)
    """
    try:
        # Build the same query as the main endpoint but for aggregation
        query = session.query(Publication).filter(Publication.contract_id.isnot(None))

        query = apply_contract_filters(
            query,
            search=search,
            year=year,
            quarter=quarter,
            month=month,
            sector_code=sector_code,
            cpv_code=cpv_code,
            region=region,
            winner=winner,
            supplier=supplier,
            buyer=buyer,
            min_value=min_value,
            max_value=max_value,
        )

        # Get aggregated results with proper join
        result = (
            query.join(Contract, Publication.contract_id == Contract.contract_id)
            .with_entities(
                func.count(Publication.publication_workspace_id).label("total_count"),
                func.sum(Contract.total_contract_amount).label("total_value"),
                func.avg(Contract.total_contract_amount).label("avg_value"),
            )
            .first()
        )

        return (
            result.total_count or 0,
            result.total_value or 0.0,
            result.avg_value or 0.0,
        )

    except Exception as e:
        logging.error(f"Error getting contracts summary: {e}")
        return 0, 0.0, 0.0
