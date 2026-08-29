"""Tools over publications (tenders), awarded or still open.

Distinct from the award tools: those look backwards at what was won, these look
at the opportunities themselves. Procy needs both -- "what similar work has been
awarded, and is anything comparable open right now" is one question to a user.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from app.config.postgres import get_session
from app.crud import company as crud_company
from app.crud.fts import (
    build_fts_condition,
    build_fts_rank,
    build_region_condition,
    build_value_condition,
)
from app.crud.publication import get_publication_by_workspace_id
from app.crud.publication_related import get_related_active_publications
from app.mcp.context import ToolContext
from app.mcp.registry import register
from app.mcp.tools.serializers import publication_to_dict
from app.models.publication_models import (
    CompanyPublicationMatch,
    Dossier,
    Organisation,
    Publication,
)

logger = logging.getLogger(__name__)

MAX_LIMIT = 50


def _eager(query):
    return query.options(
        joinedload(Publication.cpv_main_code),
        joinedload(Publication.dossier).subqueryload(Dossier.titles),
        joinedload(Publication.dossier).subqueryload(Dossier.descriptions),
        joinedload(Publication.organisation).subqueryload(
            Organisation.organisation_names
        ),
    )


@register(
    name="search_publications",
    description=(
        "Search public tenders (aanbestedingen) in the ProcLogic database, "
        "including ones that are still open for submission. Returns real "
        "records with title, buyer, deadline, CPV, value and a link."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text search in Dutch over title, description and buyer.",
            },
            "cpv_code": {
                "type": "string",
                "description": "CPV code at any precision, e.g. '45' or '45233'.",
            },
            "region": {
                "type": "array",
                "items": {"type": "string"},
                "description": "NUTS codes; prefixes match descendants ('BE2' = Flanders).",
            },
            "organisation": {
                "type": "string",
                "description": "Name of the contracting authority.",
            },
            "min_value": {"type": "number", "description": "Minimum estimated value in EUR."},
            "max_value": {"type": "number", "description": "Maximum estimated value in EUR."},
            "deadline_after": {
                "type": "string",
                "description": "ISO date; only tenders with a deadline on or after this.",
            },
            "deadline_before": {
                "type": "string",
                "description": "ISO date; only tenders with a deadline on or before this.",
            },
            "status": {
                "type": "string",
                "enum": ["open", "awarded", "any"],
                "description": (
                    "'open' = deadline still in the future, 'awarded' = already "
                    "has a gunning, 'any' = both. Default 'open'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Maximum results, 1-{MAX_LIMIT}. Default 10.",
                "minimum": 1,
                "maximum": MAX_LIMIT,
            },
        },
        "required": [],
    },
)
def search_publications(ctx: ToolContext, **params) -> Dict[str, Any]:
    limit = min(int(params.get("limit") or 10), MAX_LIMIT)
    status = (params.get("status") or "open").lower()
    query_text = params.get("query")

    with get_session() as session:
        query = session.query(Publication)

        if status == "open":
            query = query.filter(
                and_(
                    Publication.vault_submission_deadline.isnot(None),
                    Publication.vault_submission_deadline > datetime.now(),
                )
            )
        elif status == "awarded":
            query = query.filter(Publication.contract_id.isnot(None))

        for condition in (
            build_fts_condition(query_text),
            build_region_condition(params.get("region")),
            build_value_condition(
                params.get("min_value"),
                params.get("max_value"),
                Publication.estimated_value,
            ),
        ):
            if condition is not None:
                query = query.filter(condition)

        cpv = params.get("cpv_code")
        if cpv and cpv.strip():
            prefix = cpv.strip().rstrip("-0") or cpv.strip()
            query = query.filter(Publication.cpv_main_code_code.like(f"{prefix}%"))

        organisation = params.get("organisation")
        if organisation and organisation.strip():
            # searchable_content already carries every organisation name variant,
            # which avoids a join here.
            query = query.filter(
                Publication.searchable_content.ilike(f"%{organisation.strip()}%")
            )

        for field, op in (
            ("deadline_after", "ge"),
            ("deadline_before", "le"),
        ):
            raw = params.get(field)
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(str(raw))
            except ValueError:
                logger.info("Ignoring unparseable %s: %r", field, raw)
                continue
            column = Publication.vault_submission_deadline
            query = query.filter(
                column >= parsed if op == "ge" else column <= parsed
            )

        total = query.count()

        rank = build_fts_rank(query_text)
        if rank is not None:
            query = query.order_by(rank.desc(), Publication.publication_date.desc())
        else:
            query = query.order_by(Publication.publication_date.desc())

        publications = _eager(query).limit(limit).all()

        return {
            "total_matching": total,
            "returned": len(publications),
            "publications": [publication_to_dict(p) for p in publications],
        }


@register(
    name="get_publication",
    description=(
        "Full detail for one tender by workspace id: description, lots, "
        "deadline, CPV codes, estimated value, accreditations and documents."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string", "description": "The publication workspace id."}
        },
        "required": ["workspace_id"],
    },
)
def get_publication(ctx: ToolContext, workspace_id: str) -> Dict[str, Any]:
    with get_session() as session:
        publication = get_publication_by_workspace_id(
            publication_workspace_id=workspace_id, session=session
        )
        if publication is None:
            return {"found": False, "reason": f"No publication with id {workspace_id}."}

        result = publication_to_dict(publication)
        result["lots"] = [
            {
                "title": _first_text(lot.titles),
                "description": _first_text(lot.descriptions),
            }
            for lot in (publication.lots or [])
        ]
        result["additional_cpv_codes"] = [
            code.code for code in (publication.cpv_additional_codes or [])
        ]
        result["ai_summary"] = publication.ai_summary_without_documents
        result["ai_document_summary"] = publication.ai_summary_with_documents
        if publication.dossier is not None:
            result["procedure_type"] = publication.dossier.procurement_procedure_type
            result["accreditations"] = publication.dossier.accreditations

        return {"found": True, "publication": result}


def _first_text(descriptions) -> Optional[str]:
    for desc in descriptions or []:
        if getattr(desc, "text", None):
            return desc.text
    return None


@register(
    name="find_similar_publications",
    description=(
        "Find other open tenders comparable to a given one. Use this to answer "
        "'is there anything else like this currently open'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string", "description": "The tender to compare against."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["workspace_id"],
    },
)
def find_similar_publications(
    ctx: ToolContext, workspace_id: str, limit: int = 10
) -> Dict[str, Any]:
    with get_session() as session:
        publication = get_publication_by_workspace_id(
            publication_workspace_id=workspace_id, session=session
        )
        if publication is None:
            return {"found": False, "reason": f"No publication with id {workspace_id}."}

        related = get_related_active_publications(
            publication=publication, session=session, limit=min(limit, 20)
        )
        return {
            "found": True,
            "publications": [
                dict(publication_to_dict(pub), match_reason=reason)
                for pub, _score, reason in related
            ],
        }


@register(
    name="publications_with_upcoming_deadlines",
    description=(
        "Tenders your company has saved whose submission deadline falls within "
        "the next N days."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "How far ahead to look. Default 14.",
                "minimum": 1,
                "maximum": 180,
            }
        },
        "required": [],
    },
    tenant_scoped=True,
)
def publications_with_upcoming_deadlines(
    ctx: ToolContext, days: int = 14
) -> Dict[str, Any]:
    vat = ctx.require_company()
    now = datetime.now()
    horizon = now + timedelta(days=min(max(days, 1), 180))

    with get_session() as session:
        rows = (
            _eager(
                session.query(Publication)
                .join(
                    CompanyPublicationMatch,
                    CompanyPublicationMatch.publication_workspace_id
                    == Publication.publication_workspace_id,
                )
                .filter(
                    CompanyPublicationMatch.company_vat_number == vat,
                    CompanyPublicationMatch.is_saved.is_(True),
                    Publication.vault_submission_deadline.isnot(None),
                    Publication.vault_submission_deadline >= now,
                    Publication.vault_submission_deadline <= horizon,
                )
            )
            .order_by(Publication.vault_submission_deadline.asc())
            .all()
        )

        return {
            "days": days,
            "publications": [
                dict(
                    publication_to_dict(p),
                    days_left=(p.vault_submission_deadline - now).days,
                )
                for p in rows
            ],
        }


@register(
    name="get_my_company_profile",
    description=(
        "The calling company's own ProcLogic profile: activities, sectors of "
        "interest, accreditations and operating regions. Use it to judge "
        "whether an opportunity fits them."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
    tenant_scoped=True,
)
def get_my_company_profile(ctx: ToolContext) -> Dict[str, Any]:
    vat = ctx.require_company()
    with get_session() as session:
        company = crud_company.get_company_by_vat_number(
            vat_number=vat, session=session
        )
        if company is None:
            return {"found": False, "reason": "Company profile not found."}

        return {
            "found": True,
            "company": {
                "name": company.name,
                "vat_number": company.vat_number,
                "activities": company.summary_activities,
                "employees": company.number_of_employees,
                "sectors": [s.sector for s in (company.interested_sectors or [])],
                "accreditations": company.accreditations,
                "operating_regions": company.operating_regions or [],
                "max_publication_value": company.max_publication_value,
                "activity_keywords": company.activity_keywords or [],
            },
        }


@register(
    name="my_publications",
    description=(
        "Tenders the calling company has saved, or that ProcLogic recommended "
        "to them, with the match percentage."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["saved", "recommended"],
                "description": "Which list to return. Default 'saved'.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
        },
        "required": [],
    },
    tenant_scoped=True,
)
def my_publications(
    ctx: ToolContext, kind: str = "saved", limit: int = 20
) -> Dict[str, Any]:
    vat = ctx.require_company()
    limit = min(int(limit or 20), MAX_LIMIT)

    with get_session() as session:
        query = (
            session.query(Publication, CompanyPublicationMatch.match_percentage)
            .join(
                CompanyPublicationMatch,
                CompanyPublicationMatch.publication_workspace_id
                == Publication.publication_workspace_id,
            )
            .filter(CompanyPublicationMatch.company_vat_number == vat)
        )

        if kind == "recommended":
            query = query.filter(CompanyPublicationMatch.is_recommended.is_(True))
        else:
            query = query.filter(CompanyPublicationMatch.is_saved.is_(True))

        rows = (
            _eager(query).order_by(Publication.publication_date.desc()).limit(limit).all()
        )

        return {
            "kind": kind,
            "publications": [
                dict(publication_to_dict(pub), match_percentage=match)
                for pub, match in rows
            ],
        }
