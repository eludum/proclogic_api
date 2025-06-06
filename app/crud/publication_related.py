from typing import List, Optional, Tuple

from app.models.company_models import Company
from app.models.publication_models import Publication
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload


# TODO: use mcp to actually find really related stuff
def calculate_similarity_score(
    source_pub: Publication, target_pub: Publication
) -> Tuple[float, str]:
    """
    Calculate similarity score between two publications based on multiple factors.
    Returns (score, reason) where score is 0-100 and reason explains the match.
    """
    score = 0.0
    reasons = []

    # CPV code similarity (highest weight - 40 points)
    source_cpv = source_pub.cpv_main_code.code
    target_cpv = target_pub.cpv_main_code.code

    if source_cpv == target_cpv:
        score += 40
        reasons.append("Identical CPV code")
    elif source_cpv[:2] == target_cpv[:2]:  # Same sector
        score += 25
        reasons.append("Same sector")
    elif source_cpv[:4] == target_cpv[:4]:  # Same division
        score += 30
        reasons.append("Same CPV division")

    # Organization similarity (20 points)
    if source_pub.organisation_id == target_pub.organisation_id:
        score += 20
        reasons.append("Same contracting authority")

    # Geographic overlap (15 points)
    if set(source_pub.nuts_codes) & set(target_pub.nuts_codes):
        score += 15
        reasons.append("Same region")

    # Keywords similarity (15 points)
    if source_pub.extracted_keywords and target_pub.extracted_keywords:
        common_keywords = set(source_pub.extracted_keywords) & set(
            target_pub.extracted_keywords
        )
        if common_keywords:
            keyword_score = min(15, len(common_keywords) * 3)
            score += keyword_score
            reasons.append(f"Common keywords: {', '.join(list(common_keywords)[:3])}")

    # Value similarity (10 points)
    if source_pub.estimated_value and target_pub.estimated_value:
        ratio = min(source_pub.estimated_value, target_pub.estimated_value) / max(
            source_pub.estimated_value, target_pub.estimated_value
        )
        if ratio > 0.5:  # Within 50% of each other
            score += 10 * ratio
            reasons.append("Similar estimated value")

    reason = "; ".join(reasons) if reasons else "Limited similarity"
    return min(score, 100), reason


def get_related_awarded_contracts(
    publication: Publication, session: Session, limit: int = 10
) -> List[Tuple[Publication, float, str]]:
    """
    Find related awarded contracts based on the given publication.
    Returns list of (publication, similarity_score, similarity_reason).
    """
    # Get base query for awarded contracts
    query = (
        session.query(Publication)
        .filter(
            Publication.contract_id.isnot(None),
            Publication.publication_workspace_id
            != publication.publication_workspace_id,
        )
        .options(
            joinedload(Publication.cpv_main_code),
            joinedload(Publication.dossier),
            joinedload(Publication.organisation),
            joinedload(Publication.contract),
        )
    )

    # Prioritize by CPV similarity
    same_sector_filter = (
        func.substring(Publication.cpv_main_code_code, 1, 2)
        == publication.cpv_main_code.code[:2]
    )

    # Get candidates with sector preference
    candidates = query.filter(same_sector_filter).limit(50).all()

    # If not enough in same sector, get from other sectors
    if len(candidates) < limit:
        other_candidates = query.filter(~same_sector_filter).limit(limit * 2).all()
        candidates.extend(other_candidates)

    # Calculate similarity scores
    scored_contracts = []
    for candidate in candidates:
        score, reason = calculate_similarity_score(publication, candidate)
        if score > 10:  # Minimum threshold
            scored_contracts.append((candidate, score, reason))

    # Sort by score and return top results
    scored_contracts.sort(key=lambda x: x[1], reverse=True)
    return scored_contracts[:limit]


def get_related_active_publications(
    publication: Publication,
    session: Session,
    company: Optional[Company] = None,
    limit: int = 10,
) -> List[Tuple[Publication, float, str]]:
    """
    Find related active publications based on the given publication.
    Returns list of (publication, similarity_score, similarity_reason).
    """
    from datetime import datetime

    # Get base query for active publications
    query = (
        session.query(Publication)
        .filter(
            Publication.vault_submission_deadline.isnot(None),
            Publication.vault_submission_deadline > datetime.now(),
            Publication.publication_workspace_id
            != publication.publication_workspace_id,
        )
        .options(
            joinedload(Publication.cpv_main_code),
            joinedload(Publication.dossier),
            joinedload(Publication.organisation),
            joinedload(Publication.company_matches),
        )
    )

    # Prioritize by CPV similarity
    same_sector_filter = (
        func.substring(Publication.cpv_main_code_code, 1, 2)
        == publication.cpv_main_code.code[:2]
    )

    # Get candidates with sector preference
    candidates = query.filter(same_sector_filter).limit(50).all()

    # If not enough in same sector, get from other sectors
    if len(candidates) < limit:
        other_candidates = query.filter(~same_sector_filter).limit(limit * 2).all()
        candidates.extend(other_candidates)

    # Calculate similarity scores
    scored_publications = []
    for candidate in candidates:
        score, reason = calculate_similarity_score(publication, candidate)
        if score > 10:  # Minimum threshold
            scored_publications.append((candidate, score, reason))

    # Sort by score and return top results
    scored_publications.sort(key=lambda x: x[1], reverse=True)
    return scored_publications[:limit]
