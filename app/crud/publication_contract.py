import logging
from typing import List, Optional, Tuple

from sqlalchemy import and_, extract, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.publication_contract_models import Contract, ContractOrganization
from app.models.publication_models import Publication


def build_search_filter(search_term: str):
    """Build search filter for contract publications"""
    if not search_term or not search_term.strip():
        return None

    search_pattern = f"%{search_term.strip()}%"

    # Search in winner name, buyer name, and service provider name
    return or_(
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
    )


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


def get_sort_field(sort_by: str):
    """Get the appropriate sort field based on sort_by parameter"""
    if sort_by == "value":
        return Publication.contract.has(Publication.contract.total_contract_amount)
    elif sort_by == "winner":
        return Publication.contract.has(
            Publication.contract.winning_publisher.has(
                Publication.contract.winning_publisher.name
            )
        )
    elif sort_by == "buyer":
        return Publication.contract.has(
            Publication.contract.contracting_authority.has(
                Publication.contract.contracting_authority.name
            )
        )
    else:  # default to publication_date
        return Publication.publication_date


def get_paginated_contracts(
    session: Session,
    page: int = 1,
    size: int = 100,
    search: Optional[str] = None,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
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

        # Apply search filter
        search_filter = build_search_filter(search)
        if search_filter is not None:
            query = query.filter(search_filter)

        # Apply time filters
        time_filter = build_time_filter(year, quarter, month)
        if time_filter is not None:
            query = query.filter(time_filter)

        # Apply sector filter
        sector_filter = build_sector_filter(sector_code)
        if sector_filter is not None:
            query = query.filter(sector_filter)

        # Apply winner filter
        winner_filter = build_winner_filter(winner)
        if winner_filter is not None:
            query = query.filter(winner_filter)

        # Apply supplier filter
        supplier_filter = build_supplier_filter(supplier)
        if supplier_filter is not None:
            query = query.filter(supplier_filter)

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting with proper joins
        if sort_by == "value":
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
                Contract.winning_publisher_id == ContractOrganization.business_id,
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
                Contract.contracting_authority_id == ContractOrganization.business_id,
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

        # Apply pagination with basic eager loading
        # Note: Complex relationships will be loaded lazily when accessed
        publications = (
            query.options(
                joinedload(Publication.dossier),
                joinedload(Publication.organisation),
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.contract),
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
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
) -> Tuple[int, float, float]:
    """
    Get summary statistics for contracts matching the given filters.

    Returns:
        Tuple[int, float, float]: (total_count, total_value, avg_value)
    """
    try:
        # Build the same query as the main endpoint but for aggregation
        query = session.query(Publication).filter(Publication.contract_id.isnot(None))

        # Apply all the same filters
        search_filter = build_search_filter(search)
        if search_filter is not None:
            query = query.filter(search_filter)

        time_filter = build_time_filter(year, quarter, month)
        if time_filter is not None:
            query = query.filter(time_filter)

        sector_filter = build_sector_filter(sector_code)
        if sector_filter is not None:
            query = query.filter(sector_filter)

        winner_filter = build_winner_filter(winner)
        if winner_filter is not None:
            query = query.filter(winner_filter)

        supplier_filter = build_supplier_filter(supplier)
        if supplier_filter is not None:
            query = query.filter(supplier_filter)

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
