"""Builds the denormalised text blob backing the Dutch full-text index.

The tender text this project cares about is scattered: titles and descriptions
are ``Description`` rows hanging off ``Dossier`` and ``Lot``, buyer names are
``OrganisationName`` rows, and the winner is three joins away through
``Contract``. Every search path before this one paid for that at query time --
or, more often, simply never looked at the text at all.

``build_searchable_content`` flattens all of it onto ``Publication`` once, at
ingest. See migration ``c4d5e6f7a8b9``.
"""

import logging
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.publication_models import Description, Publication

logger = logging.getLogger(__name__)

# A single publication can carry a lot of lots. Past ~200k characters the blob
# stops helping recall and starts costing index size, so cut it.
MAX_SEARCHABLE_CHARS = 200_000


def _texts(descriptions: Optional[Iterable[Description]]) -> List[str]:
    """All language variants of a description set, deduplicated.

    Unlike get_descr_as_str, which picks one preferred language, this keeps every
    variant: a Dutch-speaking user may well search for a term that only appears
    in the French title, and the index costs little.
    """
    if not descriptions:
        return []
    seen = set()
    out = []
    for desc in descriptions:
        text = (getattr(desc, "text", None) or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def build_searchable_content(publication: Publication) -> str:
    """Flatten every piece of text attached to a publication into one blob.

    Safe to call on a partially-loaded publication: each relationship is guarded,
    so a missing dossier or contract just contributes nothing.
    """
    parts: List[str] = []

    dossier = getattr(publication, "dossier", None)
    if dossier is not None:
        parts.extend(_texts(getattr(dossier, "titles", None)))
        parts.extend(_texts(getattr(dossier, "descriptions", None)))
        reference = getattr(dossier, "reference_number", None)
        if reference:
            parts.append(str(reference))

    for lot in getattr(publication, "lots", None) or []:
        parts.extend(_texts(getattr(lot, "titles", None)))
        parts.extend(_texts(getattr(lot, "descriptions", None)))

    organisation = getattr(publication, "organisation", None)
    if organisation is not None:
        for org_name in getattr(organisation, "organisation_names", None) or []:
            text = (getattr(org_name, "text", None) or "").strip()
            if text:
                parts.append(text)

    for keyword in getattr(publication, "extracted_keywords", None) or []:
        if keyword:
            parts.append(str(keyword))

    for summary_attr in ("ai_summary_without_documents", "ai_summary_with_documents"):
        summary = getattr(publication, summary_attr, None)
        if summary:
            parts.append(summary)

    cpv = getattr(publication, "cpv_main_code_code", None)
    if cpv:
        parts.append(str(cpv))

    for ref_attr in (
        "publication_reference_numbers_bda",
        "publication_reference_numbers_ted",
    ):
        for ref in getattr(publication, ref_attr, None) or []:
            if ref:
                parts.append(str(ref))

    # Award-side text: the winning company and the buying authority are what
    # people actually search gunningen by.
    contract = getattr(publication, "contract", None)
    if contract is not None:
        for org_attr in (
            "winning_publisher",
            "contracting_authority",
            "service_provider",
        ):
            org = getattr(contract, org_attr, None)
            if org is None:
                continue
            for field in ("name", "business_id"):
                value = getattr(org, field, None)
                if value:
                    parts.append(str(value))

    # Deduplicate while preserving order; AI summaries in particular tend to
    # repeat the title verbatim.
    seen = set()
    unique: List[str] = []
    for part in parts:
        normalised = part.strip()
        if normalised and normalised not in seen:
            seen.add(normalised)
            unique.append(normalised)

    return "\n".join(unique)[:MAX_SEARCHABLE_CHARS]


def refresh_searchable_content(
    publication: Publication, session: Optional[Session] = None
) -> None:
    """Recompute and assign searchable_content. Never raises.

    Called from the ingest path, where a failure to build a search blob must not
    take down publication processing.
    """
    try:
        publication.searchable_content = build_searchable_content(publication)
        if session is not None:
            session.add(publication)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Failed to build searchable_content for %s: %s",
            getattr(publication, "publication_workspace_id", "<unknown>"),
            exc,
        )
