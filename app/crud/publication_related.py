from datetime import datetime
from typing import List, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.publication_models import Publication


def get_related_publications(
    publication: Publication,
    session: Session,
    include_awarded: bool = True,
    include_active: bool = True,
    limit: int = 10,
) -> List[Tuple[Publication, float, str]]:
    """
    Find related publications.

    Args:
        publication: Source publication to find similar ones for
        session: Database session
        include_awarded: Include awarded contracts in results
        include_active: Include active publications in results
        limit: Maximum number of results to return

    Returns:
        List of (publication, similarity_score, similarity_reason) tuples
    """
    # Build similarity score calculation at database level
    similarity_score = (
        # CPV code similarity (40 points max)
        case(
            (Publication.cpv_main_code_code == publication.cpv_main_code.code, 40),
            (
                func.substring(Publication.cpv_main_code_code, 1, 4)
                == publication.cpv_main_code.code[:4],
                30,
            ),
            (
                func.substring(Publication.cpv_main_code_code, 1, 2)
                == publication.cpv_main_code.code[:2],
                25,
            ),
            else_=0,
        )
        +
        # Same organization (20 points)
        case((Publication.organisation_id == publication.organisation_id, 20), else_=0)
        +
        # Geographic overlap (15 points) - using array overlap operator
        case((Publication.nuts_codes.op("&&")(publication.nuts_codes), 15), else_=0)
        +
        # Keyword similarity (15 points max) - using array overlap
        case(
            (
                and_(
                    Publication.extracted_keywords.isnot(None),
                    Publication.extracted_keywords.op("&&")(
                        publication.extracted_keywords or []
                    ),
                ),
                15,
            ),
            else_=0,
        )
        +
        # Value similarity (10 points max) - within 50% range
        case(
            (
                and_(
                    Publication.estimated_value.isnot(None),
                    Publication.estimated_value > 0,
                    publication.estimated_value is not None,
                    publication.estimated_value > 0,
                    func.least(Publication.estimated_value, publication.estimated_value)
                    / func.greatest(
                        Publication.estimated_value, publication.estimated_value
                    )
                    > 0.5,
                ),
                10,
            ),
            else_=0,
        )
    ).label("similarity_score")

    # Base query with calculated similarity
    base_query = (
        session.query(Publication, similarity_score)
        .filter(
            Publication.publication_workspace_id != publication.publication_workspace_id
        )
        .options(
            joinedload(Publication.cpv_main_code),
            joinedload(Publication.dossier),
            joinedload(Publication.organisation),
            joinedload(Publication.contract),
        )
    )

    # Filter conditions based on what to include
    filters = []

    if include_awarded:
        filters.append(Publication.contract_id.isnot(None))

    if include_active:
        filters.append(
            and_(
                Publication.vault_submission_deadline.isnot(None),
                Publication.vault_submission_deadline > datetime.now(),
            )
        )

    if filters:
        base_query = base_query.filter(or_(*filters))

    # Get results ordered by similarity score
    results = (
        base_query.filter(similarity_score > 10)  # Minimum threshold
        .order_by(similarity_score.desc())
        .limit(limit)
        .all()
    )

    # Generate reason strings
    final_results = []
    for pub, score in results:
        reasons = []

        # Check which factors contributed to the score
        if pub.cpv_main_code.code == publication.cpv_main_code.code:
            reasons.append("Identical CPV code")
        elif pub.cpv_main_code.code[:4] == publication.cpv_main_code.code[:4]:
            reasons.append("Same CPV division")
        elif pub.cpv_main_code.code[:2] == publication.cpv_main_code.code[:2]:
            reasons.append("Same sector")

        if pub.organisation_id == publication.organisation_id:
            reasons.append("Same contracting authority")

        if set(pub.nuts_codes or []) & set(publication.nuts_codes or []):
            reasons.append("Same region")

        if (
            pub.extracted_keywords
            and publication.extracted_keywords
            and set(pub.extracted_keywords) & set(publication.extracted_keywords)
        ):
            common = set(pub.extracted_keywords) & set(publication.extracted_keywords)
            reasons.append(f"Common keywords: {', '.join(list(common)[:3])}")

        if (
            pub.estimated_value
            and publication.estimated_value
            and pub.estimated_value > 0
            and publication.estimated_value > 0
            and min(pub.estimated_value, publication.estimated_value)
            / max(pub.estimated_value, publication.estimated_value)
            > 0.5
        ):
            reasons.append("Similar estimated value")

        reason = "; ".join(reasons) if reasons else "Limited similarity"
        final_results.append((pub, float(score), reason))

    return final_results


def get_related_awarded_contracts(
    publication: Publication, session: Session, limit: int = 10
) -> List[Tuple[Publication, float, str]]:
    """
    Find related awarded contracts based on the given publication.
    Returns list of (publication, similarity_score, similarity_reason).
    """
    return get_related_publications(
        publication=publication,
        session=session,
        include_awarded=True,
        include_active=False,
        limit=limit,
    )


def get_related_active_publications(
    publication: Publication, session: Session, limit: int = 10
) -> List[Tuple[Publication, float, str]]:
    """
    Find related active publications based on the given publication.
    Returns list of (publication, similarity_score, similarity_reason).
    """
    return get_related_publications(
        publication=publication,
        session=session,
        include_awarded=False,
        include_active=True,
        limit=limit,
    )
