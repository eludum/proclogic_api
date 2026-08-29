from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi_pagination import Page, Params

from app.ai.award_extraction import extract_award_from_pdf, validate_upload
from app.ai.openai import get_async_openai_client
from app.config.postgres import get_session
from app.crud import award_analytics, company_award as crud_company_award
from app.crud import company as crud_company
from app.models.company_award_document_models import MAX_UPLOAD_BYTES
from app.crud import publication as crud_publication
from app.crud.publication_contract import get_contracts_summary, get_paginated_contracts
from app.schemas.company_award_schemas import (
    AwardEntryIn,
    AwardEntryOut,
    ExtractedAward,
)
from app.schemas.publication_contract_schemas import AwardSummary, ContractItem
from app.util.publication_utils.contract import (
    convert_publications_to_contract_items,
    format_validation_errors,
    validate_filters,
)
from app.util.clerk import AuthUser, get_auth_user

contracts_router = APIRouter()


def _company_for(session, auth_user: AuthUser):
    """The caller's company, or None.

    This is the isolation boundary for everything below: the company is derived
    from the authenticated email and never read from a path, query or body, so
    there is no request a client can shape to reach another company's entries.
    """
    if not auth_user or not auth_user.email:
        return None
    return crud_company.get_company_by_email(email=auth_user.email, session=session)


def _require_company(session, auth_user: AuthUser):
    company = _company_for(session, auth_user)
    if company is None:
        raise HTTPException(
            status_code=403,
            detail="Geen bedrijf gekoppeld aan dit account.",
        )
    return company


def _entry_out(entry) -> AwardEntryOut:
    return AwardEntryOut(
        id=entry.id,
        publication_workspace_id=entry.publication_workspace_id,
        source=entry.source,
        source_document_name=entry.source_document_name,
        created_by_email=entry.created_by_email,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        supplied_fields=sorted(entry.supplied().keys()),
        title=entry.title,
        award_date=entry.award_date,
        winner=entry.winner,
        buyer=entry.buyer,
        value=entry.value,
        currency=entry.currency,
        reference_number=entry.reference_number,
        notes=entry.notes,
    )


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

        # Lay this company's own values over the BOSA ones. Scoped to the
        # caller's company, so another customer's corrections are not merely
        # hidden in the UI -- they are never loaded.
        company = _company_for(session, auth_user)
        if company is not None:
            entries = crud_company_award.get_entries_for_publications(
                session, company.vat_number, [c.publication_id for c in contracts]
            )
            for item in contracts:
                crud_company_award.merge_over(item, entries.get(item.publication_id))

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


# ---------------------------------------------------------------------------
# Company-supplied award data
#
# BOSA publishes a great many awards with the amount, the winner or the date
# missing, and customers often hold the real figures. These endpoints let a
# company record what it knows without ever touching the shared scraped row:
# see app/models/company_award_models.py. Every one of them scopes to the
# company resolved from the caller's email.
# ---------------------------------------------------------------------------


@contracts_router.get(
    "/contracts/{publication_id}/entry",
    response_model=Optional[AwardEntryOut],
)
def get_award_entry(
    publication_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """This company's own values for one award, or null if it has none."""
    with get_session() as session:
        company = _require_company(session, auth_user)
        entry = crud_company_award.get_entry(session, company.vat_number, publication_id)
        return _entry_out(entry) if entry else None


@contracts_router.put(
    "/contracts/{publication_id}/entry", response_model=AwardEntryOut
)
def put_award_entry(
    publication_id: str,
    payload: AwardEntryIn,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Record or update this company's values for an existing BOSA award.

    Only the fields present in the body are touched, so filling in a missing
    amount does not blank the rest. Sending a field as null clears it, which is
    how one field is reverted to the BOSA value without dropping the whole entry.
    """
    with get_session() as session:
        company = _require_company(session, auth_user)

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_id, session=session
        )
        if publication is None:
            raise HTTPException(status_code=404, detail="Gunning niet gevonden.")

        entry = crud_company_award.upsert_entry(
            session=session,
            company_vat_number=company.vat_number,
            created_by_email=auth_user.email,
            publication_workspace_id=publication_id,
            fields=payload.model_dump(
                exclude={"source", "source_document_name"}, exclude_unset=True
            ),
            source=payload.source,
            source_document_name=payload.source_document_name,
        )
        return _entry_out(entry)


@contracts_router.delete("/contracts/{publication_id}/entry")
def delete_award_entry(
    publication_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Drop this company's values, restoring the plain BOSA view."""
    with get_session() as session:
        company = _require_company(session, auth_user)
        removed = crud_company_award.delete_entry(
            session, company.vat_number, publication_id
        )
        if not removed:
            raise HTTPException(status_code=404, detail="Geen eigen gegevens gevonden.")
        return {"deleted": True}


@contracts_router.post("/contracts/extract-document", response_model=ExtractedAward)
async def extract_award_document(
    file: UploadFile = File(..., description="Award notice as PDF"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Read an uploaded award notice and return what the model found.

    Writes nothing. The client shows these values in the form for the user to
    check and correct, and a separate save persists them -- a model reading a
    scanned notice misreads amounts and dates often enough that storing its
    output unseen would present guesses as facts.
    """
    with get_session() as session:
        _require_company(session, auth_user)

    content = await file.read()
    rejection = validate_upload(file.filename or "", file.content_type, len(content))
    if rejection:
        raise HTTPException(status_code=400, detail=rejection)

    client = get_async_openai_client()
    return await extract_award_from_pdf(client, file.filename or "document.pdf", content)


@contracts_router.get("/company-awards", response_model=List[AwardEntryOut])
def list_company_awards(auth_user: AuthUser = Depends(get_auth_user)):
    """Awards this company entered itself, which BOSA never published."""
    with get_session() as session:
        company = _require_company(session, auth_user)
        return [
            _entry_out(e)
            for e in crud_company_award.list_company_awards(session, company.vat_number)
        ]


@contracts_router.post("/company-awards", response_model=AwardEntryOut)
def create_company_award(
    payload: AwardEntryIn,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Create an award of the company's own, with no BOSA row behind it."""
    with get_session() as session:
        company = _require_company(session, auth_user)

        fields = payload.model_dump(exclude={"source", "source_document_name"})
        if not any(v is not None for v in fields.values()):
            raise HTTPException(
                status_code=400, detail="Vul minstens één veld in."
            )

        entry = crud_company_award.upsert_entry(
            session=session,
            company_vat_number=company.vat_number,
            created_by_email=auth_user.email,
            publication_workspace_id=None,
            fields=fields,
            source=payload.source,
            source_document_name=payload.source_document_name,
        )
        return _entry_out(entry)


@contracts_router.patch(
    "/company-awards/{entry_id}", response_model=AwardEntryOut
)
def update_company_award(
    entry_id: int,
    payload: AwardEntryIn,
    auth_user: AuthUser = Depends(get_auth_user),
):
    with get_session() as session:
        company = _require_company(session, auth_user)
        entry = crud_company_award.update_by_id(
            session,
            company.vat_number,
            entry_id,
            payload.model_dump(
                exclude={"source", "source_document_name"}, exclude_unset=True
            ),
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Gunning niet gevonden.")
        return _entry_out(entry)


@contracts_router.delete("/company-awards/{entry_id}")
def delete_company_award(
    entry_id: int,
    auth_user: AuthUser = Depends(get_auth_user),
):
    with get_session() as session:
        company = _require_company(session, auth_user)
        if not crud_company_award.delete_by_id(session, company.vat_number, entry_id):
            raise HTTPException(status_code=404, detail="Gunning niet gevonden.")
        return {"deleted": True}


# ---------------------------------------------------------------------------
# Files a company attaches to an award
#
# Distinct from the BOSA annexes, which are fetched live from the procurement
# API and belong to everyone (see .../publication/{id}/documents). These are the
# customer's own: their offer, the award letter they received. Same isolation as
# every other entry -- scoped through the entry, which is scoped to the company
# resolved from the caller's email.
# ---------------------------------------------------------------------------


def _document_out(doc) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "uploaded_by_email": doc.uploaded_by_email,
        "created_at": doc.created_at,
    }


@contracts_router.get("/contracts/{publication_id}/uploads")
def list_award_uploads(
    publication_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """This company's own files for an award. Metadata only; no bytes."""
    with get_session() as session:
        company = _require_company(session, auth_user)
        entry = crud_company_award.get_entry(session, company.vat_number, publication_id)
        if entry is None:
            return {"documents": [], "total": 0}
        docs = crud_company_award.list_documents(session, company.vat_number, entry.id)
        return {"documents": [_document_out(d) for d in docs], "total": len(docs)}


@contracts_router.post("/contracts/{publication_id}/uploads")
async def upload_award_document(
    publication_id: str,
    file: UploadFile = File(..., description="Document to keep with this award"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Attach a file to an award, creating this company's entry if needed.

    Uploading is often the first thing done on an award that has no entry yet,
    so the entry is created on demand rather than making the client save an
    empty form first.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Het bestand is leeg.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Het bestand is te groot ({len(content) / 1024 / 1024:.1f} MB). "
                f"Maximaal {MAX_UPLOAD_BYTES // 1024 // 1024} MB."
            ),
        )

    with get_session() as session:
        company = _require_company(session, auth_user)

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_id, session=session
        )
        if publication is None:
            raise HTTPException(status_code=404, detail="Gunning niet gevonden.")

        entry = crud_company_award.get_entry(session, company.vat_number, publication_id)
        if entry is None:
            entry = crud_company_award.upsert_entry(
                session=session,
                company_vat_number=company.vat_number,
                created_by_email=auth_user.email,
                publication_workspace_id=publication_id,
                fields={},
            )

        document = crud_company_award.add_document(
            session=session,
            company_vat_number=company.vat_number,
            entry_id=entry.id,
            filename=file.filename or "document",
            content_type=file.content_type,
            data=content,
            uploaded_by_email=auth_user.email,
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Gunning niet gevonden.")
        return _document_out(document)


@contracts_router.get("/contracts/uploads/{document_id}")
def download_award_document(
    document_id: int,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Serve one of this company's files back.

    The lookup joins through the entry and filters on the company, so a document
    id belonging to someone else does not resolve -- it 404s rather than leaking
    that it exists.
    """
    with get_session() as session:
        company = _require_company(session, auth_user)
        document = crud_company_award.get_document(
            session, company.vat_number, document_id
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document niet gevonden.")

        # Read inside the session; the object is detached once it closes.
        payload = bytes(document.data)
        filename = document.filename
        content_type = document.content_type or "application/octet-stream"

    return Response(
        content=payload,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )


@contracts_router.delete("/contracts/uploads/{document_id}")
def delete_award_document(
    document_id: int,
    auth_user: AuthUser = Depends(get_auth_user),
):
    with get_session() as session:
        company = _require_company(session, auth_user)
        if not crud_company_award.delete_document(
            session, company.vat_number, document_id
        ):
            raise HTTPException(status_code=404, detail="Document niet gevonden.")
        return {"deleted": True}
