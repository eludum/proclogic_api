"""Turning ORM rows into the compact dicts a model reads.

Two rules apply everywhere in this module:

1. **Always include a link.** Procy is expected to cite what it found, and a
   citation the user cannot click is barely a citation. Every publication and
   award carries a ``url`` pointing at the real frontend route.
2. **Stay small.** Everything here ends up in a model context window. Full
   descriptions are truncated; the model can call get_publication for the rest.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.models.publication_models import Publication
from app.util.publication_utils.contract import (
    extract_buyer_name,
    extract_contract_value,
    extract_suppliers,
    extract_winner_name,
    get_publication_title,
)
from app.util.publication_utils.cpv_codes import get_cpv_sector_name
from app.util.publication_utils.nuts_codes import get_nuts_code_as_str
from app.util.publication_utils.publication_converter import PublicationConverter

# Descriptions in this dataset routinely run to tens of thousands of characters.
SUMMARY_CHARS = 600


def _iso(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _truncate(text: Optional[str], limit: int = SUMMARY_CHARS) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def publication_url(workspace_id: str) -> str:
    """Canonical link to the tender detail page."""
    return f"{settings.frontend_base_url.rstrip('/')}/publications/detail/{workspace_id}"


def award_url(workspace_id: str) -> str:
    """Canonical link to the gunning detail page."""
    return f"{settings.frontend_base_url.rstrip('/')}/contracts/{workspace_id}"


def _description(publication: Publication) -> Optional[str]:
    if publication.dossier and publication.dossier.descriptions:
        return PublicationConverter.get_descr_as_str(publication.dossier.descriptions)
    return None


def _organisation_name(publication: Publication) -> Optional[str]:
    if publication.organisation and publication.organisation.organisation_names:
        return PublicationConverter.get_org_name_as_str(
            publication.organisation.organisation_names
        )
    return None


def _cpv(publication: Publication) -> Optional[str]:
    return publication.cpv_main_code.code if publication.cpv_main_code else None


def _regions(publication: Publication) -> List[str]:
    return [get_nuts_code_as_str(code) for code in (publication.nuts_codes or [])]


def award_to_dict(publication: Publication, include_description: bool = True) -> Dict[str, Any]:
    """One awarded contract (gunning), as the model sees it."""
    cpv = _cpv(publication)
    contract = publication.contract

    result: Dict[str, Any] = {
        "workspace_id": publication.publication_workspace_id,
        "title": get_publication_title(publication),
        "url": award_url(publication.publication_workspace_id),
        "award_date": _iso(
            getattr(contract, "issue_date", None) or publication.publication_date
        ),
        "winner": extract_winner_name(publication),
        "buyer": extract_buyer_name(publication),
        "suppliers": extract_suppliers(publication),
        "value": extract_contract_value(publication),
        "currency": getattr(contract, "currency", None),
        "cpv_code": cpv,
        "sector": get_cpv_sector_name(cpv, "nl") if cpv else None,
        "regions": _regions(publication),
        "nuts_codes": publication.nuts_codes or [],
    }

    if contract is not None:
        result.update(
            {
                "tenders_received": contract.number_of_publications_received,
                "lowest_tender": contract.lowest_publication_amount,
                "highest_tender": contract.highest_publication_amount,
                "framework_agreement": contract.framework_agreement,
            }
        )

    if include_description:
        result["description"] = _truncate(_description(publication))

    return result


def publication_to_dict(
    publication: Publication, include_description: bool = True
) -> Dict[str, Any]:
    """One tender (active or otherwise), as the model sees it."""
    cpv = _cpv(publication)

    result: Dict[str, Any] = {
        "workspace_id": publication.publication_workspace_id,
        "title": get_publication_title(publication),
        "url": publication_url(publication.publication_workspace_id),
        "organisation": _organisation_name(publication),
        "publication_date": _iso(publication.publication_date),
        "submission_deadline": _iso(publication.vault_submission_deadline),
        "is_active": publication.is_active,
        "is_awarded": publication.contract_id is not None,
        "cpv_code": cpv,
        "sector": get_cpv_sector_name(cpv, "nl") if cpv else None,
        "regions": _regions(publication),
        "nuts_codes": publication.nuts_codes or [],
        "estimated_value": publication.estimated_value,
        "keywords": publication.extracted_keywords or [],
    }

    if include_description:
        result["description"] = _truncate(
            publication.ai_summary_without_documents or _description(publication)
        )

    return result


def candidate_to_dict(publication: Publication) -> Dict[str, Any]:
    """The narrow view handed to the retrieval agent.

    Deliberately leaner than award_to_dict: the agent may be looking at 60 of
    these at once, and everything omitted here is one the model can fetch
    individually if it decides a candidate matters.
    """
    cpv = _cpv(publication)
    return {
        "workspace_id": publication.publication_workspace_id,
        "title": get_publication_title(publication),
        "description": _truncate(_description(publication), 300),
        "buyer": extract_buyer_name(publication)
        if publication.contract
        else _organisation_name(publication),
        "winner": extract_winner_name(publication) if publication.contract else None,
        "value": extract_contract_value(publication)
        if publication.contract
        else publication.estimated_value,
        "cpv_code": cpv,
        "regions": publication.nuts_codes or [],
        "date": _iso(publication.publication_date),
    }
