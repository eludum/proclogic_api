from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from app.crud.publication import (
    get_paginated_publications_for_company,
    get_paginated_publications_free,
)
from app.models.publication_models import (
    CompanyPublicationMatch,
    Dossier,
    Lot,
    Organisation,
    Publication,
)
from app.util.publication_utils.semantic_search import semantic_search


async def get_paginated_publications_with_semantic_search(
    session: Session,
    company_vat_number: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    search_term: Optional[str] = None,
    recommended: Optional[bool] = None,
    saved: Optional[bool] = None,
    viewed: Optional[bool] = None,
    active: bool = True,
    region_filter: Optional[List[str]] = None,
    sector_filter: Optional[List[str]] = None,
    cpv_code_filter: Optional[List[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    use_semantic_search: bool = True,
    similarity_threshold: float = 0.5,
) -> Tuple[List[Publication], int]:
    """
    Enhanced publication search with semantic capabilities.

    When search_term is provided and use_semantic_search is True,
    it performs intelligent semantic search using pgai embeddings.
    Otherwise falls back to keyword search.
    """

    # If we have a search term and semantic search is enabled, use it
    if search_term and use_semantic_search:
        # First, get semantic search results
        semantic_results = await semantic_search.hybrid_search_publications(
            session=session,
            query=search_term,
            limit=size * 3,  # Get more results for filtering
            similarity_threshold=similarity_threshold,
            company_vat_number=company_vat_number,
            region_filter=region_filter,
            sector_filter=sector_filter,
            active_only=active,
        )

        if semantic_results:
            # Extract publication IDs and scores
            pub_ids = [result[0] for result in semantic_results]
            score_map = {result[0]: result[1] for result in semantic_results}

            # Build base query with semantic results
            Match = aliased(CompanyPublicationMatch)

            query = (
                session.query(Publication, Match)
                .outerjoin(
                    Match,
                    (
                        and_(
                            Match.publication_workspace_id
                            == Publication.publication_workspace_id,
                            Match.company_vat_number == company_vat_number,
                        )
                        if company_vat_number
                        else False
                    ),
                )
                .filter(Publication.publication_workspace_id.in_(pub_ids))
            )

            # Apply company-specific filters if needed
            if company_vat_number:
                if recommended is not None:
                    if recommended:
                        query = query.filter(
                            Match.company_vat_number == company_vat_number,
                            Match.is_recommended == True,
                        )
                    else:
                        query = query.filter(
                            or_(
                                Match.company_vat_number.is_(None),
                                and_(
                                    Match.company_vat_number == company_vat_number,
                                    Match.is_recommended == False,
                                ),
                            )
                        )

                if saved is not None:
                    if saved:
                        query = query.filter(
                            Match.company_vat_number == company_vat_number,
                            Match.is_saved == True,
                        )
                    else:
                        query = query.filter(
                            or_(
                                Match.company_vat_number.is_(None),
                                and_(
                                    Match.company_vat_number == company_vat_number,
                                    Match.is_saved == False,
                                ),
                            )
                        )

                if viewed is not None:
                    if viewed:
                        query = query.filter(
                            Match.company_vat_number == company_vat_number,
                            Match.is_viewed == True,
                        )
                    else:
                        query = query.filter(
                            or_(
                                Match.company_vat_number.is_(None),
                                and_(
                                    Match.company_vat_number == company_vat_number,
                                    Match.is_viewed == False,
                                ),
                            )
                        )

            # Apply date filters
            if date_from:
                query = query.filter(
                    func.date(Publication.publication_date) >= date_from
                )

            if date_to:
                query = query.filter(func.date(Publication.publication_date) <= date_to)

            # Get total count
            total_count = query.count()

            # Apply sorting - prioritize semantic score
            if sort_by == "relevance" or not sort_by:
                # Custom sorting by semantic score
                pub_order = {pub_id: idx for idx, pub_id in enumerate(pub_ids)}
                results = query.options(
                    joinedload(Publication.cpv_main_code),
                    joinedload(Publication.dossier).joinedload(Dossier.descriptions),
                    joinedload(Publication.dossier).joinedload(Dossier.titles),
                    joinedload(Publication.organisation).joinedload(
                        Organisation.organisation_names
                    ),
                    joinedload(Publication.cpv_additional_codes),
                    joinedload(Publication.lots).joinedload(Lot.descriptions),
                    joinedload(Publication.lots).joinedload(Lot.titles),
                    joinedload(Publication.company_matches),
                ).all()

                # Sort by semantic score
                sorted_results = sorted(
                    results,
                    key=lambda x: pub_order.get(
                        x[0].publication_workspace_id, float("inf")
                    ),
                )

                # Apply pagination
                start_idx = (page - 1) * size
                end_idx = start_idx + size
                paginated_results = sorted_results[start_idx:end_idx]
            else:
                # Apply regular sorting
                if sort_by == "publication_date":
                    if sort_order.lower() == "desc":
                        query = query.order_by(desc(Publication.publication_date))
                    else:
                        query = query.order_by(Publication.publication_date)
                elif sort_by == "deadline":
                    if sort_order.lower() == "desc":
                        query = query.order_by(
                            Publication.vault_submission_deadline.is_(None),
                            desc(Publication.vault_submission_deadline),
                        )
                    else:
                        query = query.order_by(
                            Publication.vault_submission_deadline.is_(None),
                            Publication.vault_submission_deadline,
                        )

                # Apply pagination
                paginated_results = (
                    query.options(
                        joinedload(Publication.cpv_main_code),
                        joinedload(Publication.dossier).joinedload(
                            Dossier.descriptions
                        ),
                        joinedload(Publication.dossier).joinedload(Dossier.titles),
                        joinedload(Publication.organisation).joinedload(
                            Organisation.organisation_names
                        ),
                        joinedload(Publication.cpv_additional_codes),
                        joinedload(Publication.lots).joinedload(Lot.descriptions),
                        joinedload(Publication.lots).joinedload(Lot.titles),
                        joinedload(Publication.company_matches),
                    )
                    .offset((page - 1) * size)
                    .limit(size)
                    .all()
                )

            # Process results
            publications = []
            for pub, match in paginated_results:
                if match:
                    pub.match_percentage = match.match_percentage
                    pub.saved_at = match.updated_at if match.is_saved else None
                    pub.viewed_at = match.updated_at if match.is_viewed else None
                else:
                    pub.match_percentage = 0
                    pub.saved_at = None
                    pub.viewed_at = None

                publications.append(pub)

            return publications, total_count

    # Fall back to regular search from the original function

    if company_vat_number:
        return get_paginated_publications_for_company(
            session=session,
            company_vat_number=company_vat_number,
            page=page,
            size=size,
            recommended=recommended,
            saved=saved,
            viewed=viewed,
            active=active,
            search_term=search_term,
            region_filter=region_filter,
            sector_filter=sector_filter,
            cpv_code_filter=cpv_code_filter,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    else:
        return get_paginated_publications_free(
            session=session,
            page=page,
            size=size,
            search_term=search_term,
            sort_by=sort_by,
            sort_order=sort_order,
            region_filter=region_filter,
            sector_filter=sector_filter,
        )
