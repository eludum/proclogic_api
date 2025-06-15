from datetime import datetime
from typing import List, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.publication_models import Publication


# TODO: optimize with AI
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
    # Prioritized scoring: Same Organization is HIGHEST priority (50 points), Keywords second (35 points), then CPV and Value
    similarity_score = (
        # Same organization (50 points) - HIGHEST PRIORITY (15 points more than keywords)
        case((Publication.organisation_id == publication.organisation_id, 50), else_=0)
        +
        # Keyword similarity (35 points max) - SECOND PRIORITY
        case(
            (
                and_(
                    Publication.extracted_keywords.isnot(None),
                    Publication.extracted_keywords.op("&&")(
                        publication.extracted_keywords or []
                    ),
                ),
                35,
            ),
            else_=0,
        )
        +
        # CPV code similarity (25 points max) - THIRD PRIORITY
        case(
            (Publication.cpv_main_code_code == publication.cpv_main_code.code, 25),
            (
                func.substring(Publication.cpv_main_code_code, 1, 4)
                == publication.cpv_main_code.code[:4],
                20,
            ),
            (
                func.substring(Publication.cpv_main_code_code, 1, 2)
                == publication.cpv_main_code.code[:2],
                15,
            ),
            else_=0,
        )
        +
        # Geographic overlap (5 points) - LOWEST PRIORITY
        case((Publication.nuts_codes.op("&&")(publication.nuts_codes), 5), else_=0)
    )

    # Add value similarity only if the publication has a valid estimated value (15 points max) - THIRD PRIORITY
    if publication.estimated_value is not None and publication.estimated_value > 0:
        value_similarity = case(
            (
                and_(
                    Publication.estimated_value.isnot(None),
                    Publication.estimated_value > 0,
                    func.least(Publication.estimated_value, publication.estimated_value)
                    / func.greatest(
                        Publication.estimated_value, publication.estimated_value
                    )
                    > 0.5,
                ),
                15,
            ),
            else_=0,
        )
        similarity_score = similarity_score + value_similarity

    similarity_score = similarity_score.label("similarity_score")

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
            reasons.append("Identieke CPV-code")
        elif pub.cpv_main_code.code[:4] == publication.cpv_main_code.code[:4]:
            reasons.append("Zelfde CPV-divisie")
        elif pub.cpv_main_code.code[:2] == publication.cpv_main_code.code[:2]:
            reasons.append("Zelfde sector")

        if pub.organisation_id == publication.organisation_id:
            reasons.append("Zelfde aanbestedende dienst")

        if set(pub.nuts_codes or []) & set(publication.nuts_codes or []):
            reasons.append("Zelfde regio")

        if (
            pub.extracted_keywords
            and publication.extracted_keywords
            and set(pub.extracted_keywords) & set(publication.extracted_keywords)
        ):
            common = set(pub.extracted_keywords) & set(publication.extracted_keywords)
            reasons.append(
                f"Gemeenschappelijke trefwoorden: {', '.join(list(common)[:3])}"
            )

        # Fixed the estimated value comparison to handle None values properly
        if (
            pub.estimated_value is not None
            and publication.estimated_value is not None
            and pub.estimated_value > 0
            and publication.estimated_value > 0
            and min(pub.estimated_value, publication.estimated_value)
            / max(pub.estimated_value, publication.estimated_value)
            > 0.5
        ):
            reasons.append("Vergelijkbare geschatte waarde")

        reason = "; ".join(reasons) if reasons else "Beperkte overeenkomst"
        final_results.append((pub, float(score), reason))

    return final_results


def get_related_awarded_contracts(
    publication: Publication, session: Session, limit: int = 10
) -> List[Tuple[Publication, float, str]]:
    """
    Find related awarded contracts based on the given publication.
    Returns list of (publication, similarity_score, similarity_reason).
    """
    # TODO: use pgai here too?
    return get_related_publications(
        publication=publication,
        session=session,
        include_awarded=True,
        include_active=False,
        limit=limit,
    )
