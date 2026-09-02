import logging
from typing import List, Optional, Tuple

from sqlalchemy import and_, extract, func
from sqlalchemy.orm import Session, selectinload

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

    Matches the flattened Dutch full-text blob, which build_searchable_content()
    already fills with the winner, the contracting authority and the service
    provider -- name and business_id both -- alongside the title, descriptions
    and lots.

    This used to OR four correlated ``EXISTS ... lower(name) LIKE '%term%'``
    subqueries over contract_organizations next to the full-text arm, because
    searchable_content could still be NULL on rows predating its backfill. That
    backfill has since completed (0 NULL rows, awards included) and ingest fills
    the column, so those arms matched nothing the full-text arm did not.

    They were not merely redundant, they were fatal. Postgres cannot answer a
    disjunction from an index unless it can answer every branch from one, so
    ORing unindexable correlated subqueries beside the indexed tsvector match
    dragged the whole query onto a sequential scan of 107k publications with
    four correlated lookups per row. Measured with the retrieval agent's own
    seed term: the organisation arms alone 0.46s, the full-text arm alone 0.19s,
    the two ORed together **30s -- the statement timeout**. Which is precisely
    why the agent silently returned nothing and /related fell back to the
    deterministic scorer.
    """
    if not search_term or not search_term.strip():
        return None

    return build_fts_condition(search_term)


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

        # selectinload everywhere, joinedload nowhere -- and here that is a
        # planner decision, not a cartesian-product one.
        #
        # joinedload adds its LEFT OUTER JOINs to *this* statement, and the
        # extra joins change what the planner thinks the ORDER BY ... LIMIT 25
        # costs. With them it abandons the bitmap scan over the FTS and trigram
        # indexes and walks idx_publications_publication_date backwards
        # instead, re-evaluating `to_tsvector(searchable_content) @@ query OR
        # searchable_content ILIKE '%term%'` as a *filter* on every row it
        # passes, betting it will collect 25 matches early and stop.
        #
        # On a term that matches nothing that bet loses completely: it filters
        # all 107k publications, recomputing a tsvector over the whole text
        # blob for each. Measured against prod on 2026-09-02 with the term that
        # took the endpoint down -- 'sxde', 0 matches:
        #
        #     count()                      0.05s
        #     the same query, no options   0.03s
        #     ... with joinedload         26.34s   <- 30s statement_timeout
        #     ... with selectinload        0.08s
        #
        # selectinload leaves this statement join-free, so the planner keeps the
        # bitmap scan and the relationships load in follow-up SELECTs keyed on
        # the 25 ids it returned. The normal case gets faster too (a matching
        # term: 1.83s -> 0.90s), because those SELECTs replace a row that
        # carried every joined table's columns at once.
        publications = (
            query.options(
                # Load dossier and its nested relationships
                selectinload(Publication.dossier).selectinload(Dossier.titles),
                selectinload(Publication.dossier).selectinload(Dossier.descriptions),
                # Load organisation
                selectinload(Publication.organisation),
                # Load CPV code
                selectinload(Publication.cpv_main_code),
                # Load contract with organizations
                selectinload(Publication.contract).selectinload(Contract.winning_publisher),
                selectinload(Publication.contract).selectinload(
                    Contract.contracting_authority
                ),
                selectinload(Publication.contract).selectinload(Contract.service_provider),
            )
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        return publications, total_count

    except Exception as e:
        # Roll back first. A statement that hit the 30s statement_timeout
        # leaves the transaction aborted, and every later query on this session
        # -- in the same request -- then fails with InFailedSqlTransaction.
        # 2026-09-02 23:26 is what that looks like: the timeout here took the
        # caller's own company lookup down with it, and because that swallows
        # its errors too and returns None, the request answered 200 with an
        # empty award list and none of the company's own corrections applied.
        session.rollback()
        logging.error("Error getting paginated contracts: %s", e)
        # Then raise, rather than reporting a failed search as a search that
        # found nothing. "0 awards" is an answer callers act on -- the endpoint
        # renders an empty page, the MCP tool tells the model there are no such
        # awards -- and it is the wrong one. The one caller that genuinely
        # wants best-effort recall is _seed_candidates, whose candidate pool is
        # explicitly optional; it now says so by catching this itself.
        raise


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
