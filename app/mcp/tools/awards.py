"""Tools over awarded contracts (gunningen).

These are what turn "similar gunningen" from a guess into a lookup: every one of
them returns rows that exist in the database, with a link to the page that shows
them.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import joinedload

from app.config.postgres import get_session
from app.crud import award_analytics
from app.crud.publication_contract import (
    get_contracts_summary,
    get_paginated_contracts,
)
from app.mcp.context import ToolContext
from app.mcp.registry import register
from app.mcp.tools.serializers import award_to_dict
from app.models.publication_contract_models import Contract
from app.models.publication_models import Publication

logger = logging.getLogger(__name__)

MAX_LIMIT = 50

# Shared filter vocabulary. Spelled out once so every award tool accepts exactly
# the same filters -- a model that learns them on search_awards can apply them
# unchanged to any breakdown.
_FILTER_PROPERTIES: Dict[str, Any] = {
    "query": {
        "type": "string",
        "description": (
            "Free-text search in Dutch over title, description, lots, buyer and "
            "winner. Use the words a tender would actually use, e.g. "
            "'dakwerken schoolgebouw'."
        ),
    },
    "year": {"type": "integer", "description": "Filter on publication year."},
    "quarter": {"type": "integer", "description": "Quarter 1-4.", "minimum": 1, "maximum": 4},
    "month": {"type": "integer", "description": "Month 1-12.", "minimum": 1, "maximum": 12},
    "sector_code": {
        "type": "string",
        "description": "CPV sector, first two digits, e.g. '45' for construction.",
    },
    "cpv_code": {
        "type": "string",
        "description": (
            "CPV code at any precision, e.g. '45233' matches all road works. "
            "More precise than sector_code."
        ),
    },
    "region": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "NUTS codes; prefixes match descendants, so 'BE2' covers all of "
            "Flanders and 'BE23' covers Oost-Vlaanderen."
        ),
    },
    "winner": {"type": "string", "description": "Name of the winning company."},
    "supplier": {"type": "string", "description": "Name of a named service provider."},
    "buyer": {"type": "string", "description": "Name of the contracting authority."},
    "min_value": {"type": "number", "description": "Minimum awarded amount in EUR."},
    "max_value": {"type": "number", "description": "Maximum awarded amount in EUR."},
}


def _filters_from(params: Dict[str, Any]) -> Dict[str, Any]:
    """Map the tool's parameter names onto the CRUD filter names."""
    return {
        "search": params.get("query"),
        "year": params.get("year"),
        "quarter": params.get("quarter"),
        "month": params.get("month"),
        "sector_code": params.get("sector_code"),
        "cpv_code": params.get("cpv_code"),
        "region": params.get("region"),
        "winner": params.get("winner"),
        "supplier": params.get("supplier"),
        "buyer": params.get("buyer"),
        "min_value": params.get("min_value"),
        "max_value": params.get("max_value"),
    }


def _schema(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    properties = dict(_FILTER_PROPERTIES)
    if extra:
        properties.update(extra)
    return {"type": "object", "properties": properties, "required": []}


@register(
    name="search_awards",
    description=(
        "Search awarded public contracts (gunningen) in the ProcLogic database. "
        "Returns real records with title, winner, buyer, value, date and a link. "
        "Use this instead of answering about past awards from memory."
    ),
    parameters=_schema(
        {
            "limit": {
                "type": "integer",
                "description": f"Maximum results, 1-{MAX_LIMIT}. Default 10.",
                "minimum": 1,
                "maximum": MAX_LIMIT,
            },
            "sort_by": {
                "type": "string",
                "enum": ["relevance", "publication_date", "value", "winner", "buyer"],
                "description": "Default 'relevance' when a query is given, else newest first.",
            },
            "sort_order": {"type": "string", "enum": ["asc", "desc"]},
        }
    ),
)
def search_awards(ctx: ToolContext, **params) -> Dict[str, Any]:
    limit = min(int(params.get("limit") or 10), MAX_LIMIT)
    sort_by = params.get("sort_by") or ("relevance" if params.get("query") else "publication_date")

    with get_session() as session:
        publications, total = get_paginated_contracts(
            session=session,
            page=1,
            size=limit,
            sort_by=sort_by,
            sort_order=params.get("sort_order") or "desc",
            **_filters_from(params),
        )
        return {
            "total_matching": total,
            "returned": len(publications),
            "awards": [award_to_dict(p) for p in publications],
        }


@register(
    name="get_award",
    description=(
        "Full detail for one awarded contract by its workspace id, including "
        "tender counts and the lowest/highest bids where published."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "The publication workspace id of the award.",
            }
        },
        "required": ["workspace_id"],
    },
)
def get_award(ctx: ToolContext, workspace_id: str) -> Dict[str, Any]:
    with get_session() as session:
        publication = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id == workspace_id)
            .options(
                joinedload(Publication.dossier),
                joinedload(Publication.organisation),
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.contract).joinedload(Contract.winning_publisher),
                joinedload(Publication.contract).joinedload(
                    Contract.contracting_authority
                ),
                joinedload(Publication.contract).joinedload(Contract.service_provider),
            )
            .first()
        )

        if publication is None:
            return {"found": False, "reason": f"No publication with id {workspace_id}."}
        if publication.contract is None:
            return {
                "found": False,
                "reason": (
                    f"Publication {workspace_id} exists but has not been awarded, "
                    "so it is a tender rather than a gunning. Use get_publication."
                ),
            }

        return {"found": True, "award": award_to_dict(publication)}


@register(
    name="award_market_stats",
    description=(
        "Aggregate statistics (count, total value, average value) over awarded "
        "contracts matching the filters. Use this for questions about market "
        "size rather than listing individual awards."
    ),
    parameters=_schema(),
)
def award_market_stats(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        total_count, total_value, avg_value = get_contracts_summary(
            session=session, **_filters_from(params)
        )
        return {
            "total_count": total_count,
            "total_value": float(total_value or 0.0),
            "avg_value": float(avg_value or 0.0),
            "currency": "EUR",
        }


def _breakdown_schema() -> Dict[str, Any]:
    return _schema(
        {
            "limit": {
                "type": "integer",
                "description": "Number of groups to return. Default 25, max 200.",
                "minimum": 1,
                "maximum": 200,
            }
        }
    )


@register(
    name="awards_by_sector",
    description="Award count and value grouped by CPV sector.",
    parameters=_breakdown_schema(),
)
def awards_by_sector_tool(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        return {
            "sectors": award_analytics.awards_by_sector(
                session, limit=params.get("limit"), **_filters_from(params)
            )
        }


@register(
    name="awards_by_region",
    description=(
        "Award count and value grouped by NUTS region. A publication covering "
        "several regions is counted in each, so group totals exceed the overall "
        "total."
    ),
    parameters=_breakdown_schema(),
)
def awards_by_region_tool(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        return {
            "regions": award_analytics.awards_by_region(
                session, limit=params.get("limit"), **_filters_from(params)
            )
        }


@register(
    name="awards_by_winner",
    description=(
        "Which companies win these contracts, how many they won and for how "
        "much. Use this to answer 'who usually wins this kind of work'."
    ),
    parameters=_breakdown_schema(),
)
def awards_by_winner_tool(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        return {
            "winners": award_analytics.awards_by_winner(
                session, limit=params.get("limit"), **_filters_from(params)
            )
        }


@register(
    name="awards_by_supplier",
    description="Named service providers on awards, ranked by total value.",
    parameters=_breakdown_schema(),
)
def awards_by_supplier_tool(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        return {
            "suppliers": award_analytics.awards_by_supplier(
                session, limit=params.get("limit"), **_filters_from(params)
            )
        }


@register(
    name="awards_by_buyer",
    description=(
        "Contracting authorities ranked by what they award. Use this to answer "
        "'which buyers spend most on this kind of work'."
    ),
    parameters=_breakdown_schema(),
)
def awards_by_buyer_tool(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        return {
            "buyers": award_analytics.awards_by_buyer(
                session, limit=params.get("limit"), **_filters_from(params)
            )
        }


@register(
    name="awards_timeseries",
    description=(
        "Award count and value over time, bucketed by month, quarter or year. "
        "Use this for trend questions."
    ),
    parameters=_schema(
        {
            "granularity": {
                "type": "string",
                "enum": ["month", "quarter", "year"],
                "description": "Bucket size. Default 'month'.",
            }
        }
    ),
)
def awards_timeseries_tool(ctx: ToolContext, **params) -> Dict[str, Any]:
    with get_session() as session:
        return {
            "series": award_analytics.awards_timeseries(
                session,
                granularity=params.get("granularity") or "month",
                **_filters_from(params),
            )
        }


@register(
    name="find_similar_awards",
    description=(
        "Find awarded contracts comparable to a given tender. Searches the "
        "database and ranks what it finds; every result is a real award with a "
        "link. Use this whenever asked what similar work has been awarded "
        "before, or what such work tends to cost."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "Workspace id of the tender to find comparable awards for.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results, default 10.",
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["workspace_id"],
    },
)
def find_similar_awards(
    ctx: ToolContext, workspace_id: str, limit: int = 10
) -> Dict[str, Any]:
    # Imported lazily: the retrieval agent calls back into this registry, so a
    # module-level import would be circular.
    from app.ai.retrieval_agent import find_similar_awards_sync

    results = find_similar_awards_sync(workspace_id=workspace_id, limit=limit)
    return {"count": len(results), "similar_awards": results}
