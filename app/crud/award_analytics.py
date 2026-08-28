"""Aggregate breakdowns over awarded contracts (gunningen).

Every function here shares the filter set in
``app.crud.publication_contract.apply_contract_filters``, so a breakdown always
reconciles with ``get_contracts_summary`` over the same filters.

Aggregation happens in SQL. An earlier attempt at this surface (the abandoned
``origin/analytics_rewrite`` branch) pulled every matching row into Python with
``query.all()`` and summed there; it also read a ``Publication.award`` JSON
column that migration ``9dc262f2c7ac`` dropped. Neither approach survives here.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from app.crud.publication_contract import apply_contract_filters
from app.models.publication_contract_models import Contract, ContractOrganization
from app.models.publication_models import Publication
from app.util.publication_utils.cpv_codes import get_cpv_sector_name
from app.util.publication_utils.nuts_codes import get_nuts_code_as_str

logger = logging.getLogger(__name__)

# Guard rail for every grouped query: without it a caller could ask for one row
# per winner across the whole database and hand the model a 50k-row table.
DEFAULT_GROUP_LIMIT = 25
MAX_GROUP_LIMIT = 200

_GRANULARITIES = {"month": "month", "quarter": "quarter", "year": "year"}


def _base_query(session: Session, **filters):
    """Awards only, with every requested filter applied."""
    query = session.query(Publication).filter(Publication.contract_id.isnot(None))
    return apply_contract_filters(query, **filters)


def _with_contract(query):
    return query.join(Contract, Publication.contract_id == Contract.contract_id)


def _clamp(limit: Optional[int]) -> int:
    if not limit or limit < 1:
        return DEFAULT_GROUP_LIMIT
    return min(limit, MAX_GROUP_LIMIT)


def _money(value) -> float:
    return float(value) if value is not None else 0.0


def awards_by_sector(
    session: Session, limit: Optional[int] = None, **filters
) -> List[Dict[str, Any]]:
    """Award count and value per CPV sector (the first two digits of the code)."""
    try:
        limit = _clamp(limit)
        sector_code = func.substr(Publication.cpv_main_code_code, 1, 2)

        rows = (
            _with_contract(_base_query(session, **filters))
            .with_entities(
                sector_code.label("sector_prefix"),
                func.count(Publication.publication_workspace_id).label("count"),
                func.sum(Contract.total_contract_amount).label("total_value"),
                func.avg(Contract.total_contract_amount).label("avg_value"),
            )
            .group_by(sector_code)
            .order_by(func.sum(Contract.total_contract_amount).desc().nullslast())
            .limit(limit)
            .all()
        )

        return [
            {
                "sector_code": row.sector_prefix,
                "sector": get_cpv_sector_name(f"{row.sector_prefix}000000", "nl"),
                "count": row.count,
                "total_value": _money(row.total_value),
                "avg_value": _money(row.avg_value),
            }
            for row in rows
            if row.sector_prefix
        ]
    except Exception as exc:
        logger.error("awards_by_sector failed: %s", exc)
        return []


def awards_by_region(
    session: Session, limit: Optional[int] = None, **filters
) -> List[Dict[str, Any]]:
    """Award count and value per NUTS code.

    nuts_codes is an array column, so a publication covering several regions is
    counted once per region. Totals therefore do not sum to the overall total --
    that is inherent to the data, not a bug.
    """
    try:
        limit = _clamp(limit)
        nuts = func.unnest(Publication.nuts_codes).label("nuts_code")

        subquery = (
            _with_contract(_base_query(session, **filters))
            .with_entities(
                nuts,
                Contract.total_contract_amount.label("amount"),
                Publication.publication_workspace_id.label("workspace_id"),
            )
            .subquery()
        )

        rows = (
            session.query(
                subquery.c.nuts_code,
                func.count(subquery.c.workspace_id).label("count"),
                func.sum(subquery.c.amount).label("total_value"),
                func.avg(subquery.c.amount).label("avg_value"),
            )
            .group_by(subquery.c.nuts_code)
            .order_by(func.sum(subquery.c.amount).desc().nullslast())
            .limit(limit)
            .all()
        )

        return [
            {
                "nuts_code": row.nuts_code,
                "region": get_nuts_code_as_str(row.nuts_code),
                "count": row.count,
                "total_value": _money(row.total_value),
                "avg_value": _money(row.avg_value),
            }
            for row in rows
            if row.nuts_code
        ]
    except Exception as exc:
        logger.error("awards_by_region failed: %s", exc)
        return []


def _by_organisation(
    session: Session,
    join_column,
    limit: Optional[int] = None,
    **filters,
) -> List[Dict[str, Any]]:
    """Shared body for the winner / supplier / buyer breakdowns."""
    limit = _clamp(limit)
    org = aliased(ContractOrganization)

    rows = (
        _with_contract(_base_query(session, **filters))
        .join(org, join_column == org.id)
        .with_entities(
            org.id.label("org_id"),
            org.name.label("name"),
            org.business_id.label("business_id"),
            func.count(Publication.publication_workspace_id).label("count"),
            func.sum(Contract.total_contract_amount).label("total_value"),
            func.avg(Contract.total_contract_amount).label("avg_value"),
            # .distinct() on the argument renders array_agg(DISTINCT ...);
            # func.distinct(...) would render a distinct() call Postgres rejects.
            func.array_agg(
                func.substr(Publication.cpv_main_code_code, 1, 2).distinct()
            ).label("sector_prefixes"),
        )
        .group_by(org.id, org.name, org.business_id)
        .order_by(func.sum(Contract.total_contract_amount).desc().nullslast())
        .limit(limit)
        .all()
    )

    results = []
    for row in rows:
        sectors = [
            get_cpv_sector_name(f"{prefix}000000", "nl")
            for prefix in (row.sector_prefixes or [])
            if prefix
        ]
        results.append(
            {
                "organisation_id": row.org_id,
                "name": row.name,
                "vat_number": row.business_id,
                "count": row.count,
                "total_value": _money(row.total_value),
                "avg_value": _money(row.avg_value),
                "sectors": sorted(set(sectors)),
            }
        )
    return results


def awards_by_winner(
    session: Session, limit: Optional[int] = None, **filters
) -> List[Dict[str, Any]]:
    """Who wins, how often, and for how much."""
    try:
        return _by_organisation(
            session, Contract.winning_publisher_id, limit=limit, **filters
        )
    except Exception as exc:
        logger.error("awards_by_winner failed: %s", exc)
        return []


def awards_by_supplier(
    session: Session, limit: Optional[int] = None, **filters
) -> List[Dict[str, Any]]:
    """Service providers named on awards."""
    try:
        return _by_organisation(
            session, Contract.service_provider_id, limit=limit, **filters
        )
    except Exception as exc:
        logger.error("awards_by_supplier failed: %s", exc)
        return []


def awards_by_buyer(
    session: Session, limit: Optional[int] = None, **filters
) -> List[Dict[str, Any]]:
    """Contracting authorities, ranked by what they spend."""
    try:
        return _by_organisation(
            session, Contract.contracting_authority_id, limit=limit, **filters
        )
    except Exception as exc:
        logger.error("awards_by_buyer failed: %s", exc)
        return []


def awards_timeseries(
    session: Session, granularity: str = "month", **filters
) -> List[Dict[str, Any]]:
    """Award count and value over time.

    Buckets on publication_date rather than Contract.issue_date: issue_date is
    frequently missing on older notices, and a timeseries that silently drops
    those rows would not reconcile with the summary.
    """
    try:
        unit = _GRANULARITIES.get((granularity or "month").lower(), "month")
        bucket = func.date_trunc(unit, Publication.publication_date).label("bucket")

        rows = (
            _with_contract(_base_query(session, **filters))
            .with_entities(
                bucket,
                func.count(Publication.publication_workspace_id).label("count"),
                func.sum(Contract.total_contract_amount).label("total_value"),
                func.avg(Contract.total_contract_amount).label("avg_value"),
            )
            .group_by(bucket)
            .order_by(bucket.asc())
            .all()
        )

        return [
            {
                "period": row.bucket.date().isoformat() if row.bucket else None,
                "granularity": unit,
                "count": row.count,
                "total_value": _money(row.total_value),
                "avg_value": _money(row.avg_value),
            }
            for row in rows
            if row.bucket
        ]
    except Exception as exc:
        logger.error("awards_timeseries failed: %s", exc)
        return []
