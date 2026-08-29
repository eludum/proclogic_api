"""Lookups for the entities that appear in procurement data.

Buyers and winners are the entities users actually ask about by name -- "wat
koopt Stad Gent" or "wat wint Besix" -- and CPV/NUTS codes are the vocabulary
everything else is filtered by. Without these, the model has to guess the code
for a sector or a province, and guessing a filter value produces a confidently
empty result set.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from app.config.postgres import get_session
from app.crud import award_analytics
from app.mcp.context import ToolContext
from app.mcp.registry import register
from app.models.publication_contract_models import Contract, ContractOrganization
from app.models.publication_models import Publication
from app.util.publication_utils.cpv_codes import nl_sectors
from app.util.publication_utils.nuts_codes import nuts_codes

logger = logging.getLogger(__name__)

MAX_LIMIT = 50


@register(
    name="search_organisations",
    description=(
        "Find organisations that appear in awards -- contracting authorities "
        "(buyers) and winning companies -- by name or VAT number. Returns their "
        "id so you can call get_organisation_profile."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Full or partial name, or a VAT/business id.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
        },
        "required": ["name"],
    },
)
def search_organisations(
    ctx: ToolContext, name: str, limit: int = 15
) -> Dict[str, Any]:
    limit = min(int(limit or 15), MAX_LIMIT)
    pattern = f"%{(name or '').strip()}%"
    if not (name or "").strip():
        return {"organisations": []}

    with get_session() as session:
        rows = (
            session.query(ContractOrganization)
            .filter(
                or_(
                    ContractOrganization.name.ilike(pattern),
                    ContractOrganization.business_id.ilike(pattern),
                )
            )
            .limit(limit)
            .all()
        )

        return {
            "organisations": [
                {
                    "organisation_id": org.id,
                    "name": org.name,
                    "vat_number": org.business_id,
                    "website": org.website,
                    "company_size": org.company_size,
                }
                for org in rows
            ]
        }


@register(
    name="get_organisation_profile",
    description=(
        "What an organisation does in public procurement: how much it has won "
        "as a supplier, how much it has awarded as a buyer, in which sectors, "
        "and who it deals with."
    ),
    parameters={
        "type": "object",
        "properties": {
            "organisation_id": {
                "type": "integer",
                "description": "Id from search_organisations.",
            },
            "name": {
                "type": "string",
                "description": "Alternatively, the organisation name or VAT number.",
            },
        },
        "required": [],
    },
)
def get_organisation_profile(
    ctx: ToolContext,
    organisation_id: Optional[int] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    with get_session() as session:
        org = None
        if organisation_id is not None:
            org = (
                session.query(ContractOrganization)
                .filter(ContractOrganization.id == organisation_id)
                .first()
            )
        elif name and name.strip():
            pattern = f"%{name.strip()}%"
            org = (
                session.query(ContractOrganization)
                .filter(
                    or_(
                        ContractOrganization.name.ilike(pattern),
                        ContractOrganization.business_id.ilike(pattern),
                    )
                )
                .first()
            )

        if org is None:
            return {
                "found": False,
                "reason": "No matching organisation. Try search_organisations first.",
            }

        def _role_stats(column) -> Dict[str, Any]:
            row = (
                session.query(
                    func.count(Publication.publication_workspace_id).label("count"),
                    func.sum(Contract.total_contract_amount).label("total"),
                    func.avg(Contract.total_contract_amount).label("avg"),
                    func.min(Publication.publication_date).label("first"),
                    func.max(Publication.publication_date).label("last"),
                )
                .select_from(Publication)
                .join(Contract, Publication.contract_id == Contract.contract_id)
                .filter(column == org.id)
                .first()
            )
            return {
                "count": row.count or 0,
                "total_value": float(row.total or 0.0),
                "avg_value": float(row.avg or 0.0),
                "first_seen": row.first.isoformat() if row.first else None,
                "last_seen": row.last.isoformat() if row.last else None,
            }

        as_winner = _role_stats(Contract.winning_publisher_id)
        as_buyer = _role_stats(Contract.contracting_authority_id)

        profile: Dict[str, Any] = {
            "found": True,
            "organisation": {
                "organisation_id": org.id,
                "name": org.name,
                "vat_number": org.business_id,
                "website": org.website,
                "company_size": org.company_size,
            },
            "as_winner": as_winner,
            "as_buyer": as_buyer,
        }

        # Only compute the expensive breakdowns for the role the organisation
        # actually plays, so a pure buyer does not pay for an empty winner query.
        if as_winner["count"]:
            profile["sectors_won"] = award_analytics.awards_by_sector(
                session, limit=10, winner=org.name
            )
            profile["buyers_dealt_with"] = award_analytics.awards_by_buyer(
                session, limit=10, winner=org.name
            )
        if as_buyer["count"]:
            profile["sectors_bought"] = award_analytics.awards_by_sector(
                session, limit=10, buyer=org.name
            )
            profile["suppliers_used"] = award_analytics.awards_by_winner(
                session, limit=10, buyer=org.name
            )

        return profile


@register(
    name="lookup_cpv",
    description=(
        "Resolve a CPV sector: give a two-digit code to get its Dutch name, or "
        "give a description to find matching sector codes. Use this before "
        "filtering by sector_code so you filter on a code that exists."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A CPV code ('45') or a description ('bouwwerkzaamheden').",
            }
        },
        "required": ["query"],
    },
)
def lookup_cpv(ctx: ToolContext, query: str) -> Dict[str, Any]:
    term = (query or "").strip()
    if not term:
        return {"matches": []}

    matches: List[Dict[str, str]] = []

    if term[:2].isdigit():
        key = term[:2] + "000000"
        if key in nl_sectors:
            matches.append(
                {"sector_code": term[:2], "cpv_code": key, "name": nl_sectors[key]}
            )

    lowered = term.lower()
    for code, label in nl_sectors.items():
        if lowered in label.lower() and not any(
            m["cpv_code"] == code for m in matches
        ):
            matches.append({"sector_code": code[:2], "cpv_code": code, "name": label})

    return {"matches": matches[:20]}


@register(
    name="lookup_nuts",
    description=(
        "Resolve a Belgian NUTS region code: give a code to get its name, or a "
        "place name to get its code. Use this before filtering by region."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A NUTS code ('BE23') or a place name ('Oost-Vlaanderen').",
            }
        },
        "required": ["query"],
    },
)
def lookup_nuts(ctx: ToolContext, query: str) -> Dict[str, Any]:
    term = (query or "").strip()
    if not term:
        return {"matches": []}

    upper = term.upper()
    lowered = term.lower()
    matches = []

    for code, label in nuts_codes.items():
        if code == upper or lowered in label.lower():
            matches.append({"nuts_code": code, "name": label})

    # Prefer exact code hits, then shorter (broader) codes first.
    matches.sort(key=lambda m: (m["nuts_code"] != upper, len(m["nuts_code"])))
    return {"matches": matches[:25]}
