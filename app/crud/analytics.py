from typing import Dict, List, Optional

from sqlalchemy import and_, extract, func
from sqlalchemy.orm import Session

from app.models.publication_models import CPVCode, Publication


def get_awards_summary(
    session: Session,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
) -> Dict[str, float]:
    """
    Get summary statistics about awarded contracts.
    Returns dictionary with total_value, total_count, and avg_value.
    """
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply time period filter
    time_filter = get_time_period_filter(year, quarter, month)
    if time_filter:
        query = query.filter(time_filter)

    # Apply sector filter
    if sector_code:
        sector_filter = get_sector_filter(sector_code)
        if sector_filter:
            query = query.join(Publication.cpv_main_code).filter(sector_filter)

    # Apply winner filter
    if winner:
        query = query.filter(Publication.award["winner"].astext.ilike(f"%{winner}%"))

    # Apply supplier filter
    if supplier:
        query = query.filter(
            Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
        )

    publications = query.all()

    # Calculate statistics
    count = len(publications)
    total_value = sum(get_award_value(pub) for pub in publications)
    avg_value = total_value / count if count > 0 else 0

    return {"total_value": total_value, "total_count": count, "avg_value": avg_value}


def get_awards_timeseries(
    session: Session,
    period_type: str = "monthly",
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
) -> List[Dict]:
    """
    Get time series data for awarded contracts.
    """
    # Base query to get all awarded publications with required data
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply year filter if provided
    if year:
        query = query.filter(extract("year", Publication.publication_date) == year)

    # Apply sector filter if provided
    if sector_code:
        sector_filter = get_sector_filter(sector_code)
        if sector_filter:
            query = query.join(Publication.cpv_main_code).filter(sector_filter)

    # Apply winner filter if provided
    if winner:
        query = query.filter(Publication.award["winner"].astext.ilike(f"%{winner}%"))

    # Apply supplier filter if provided
    if supplier:
        query = query.filter(
            Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
        )

    publications = query.all()

    # Convert to dictionaries for processing
    data = [
        {"date": pub.publication_date, "value": get_award_value(pub)}
        for pub in publications
    ]

    return data


def get_awards_by_sector(
    session: Session,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
) -> List[Dict]:
    """
    Get awarded contracts grouped by sector.
    """
    # Base query to get all awarded publications
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply time period filter
    time_filter = get_time_period_filter(year, quarter, month)
    if time_filter:
        query = query.filter(time_filter)

    # Apply winner filter
    if winner:
        query = query.filter(Publication.award["winner"].astext.ilike(f"%{winner}%"))

    # Apply supplier filter
    if supplier:
        query = query.filter(
            Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
        )

    publications = query.all()
    return publications


def get_awards_by_region(
    session: Session,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
) -> List[Publication]:
    """
    Get award counts and values grouped by geographic regions.
    """
    # Base query to get all awarded publications
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply time period filter
    time_filter = get_time_period_filter(year, quarter, month)
    if time_filter:
        query = query.filter(time_filter)

    # Apply sector filter
    if sector_code:
        sector_filter = get_sector_filter(sector_code)
        if sector_filter:
            query = query.join(Publication.cpv_main_code).filter(sector_filter)

    # Apply winner filter
    if winner:
        query = query.filter(Publication.award["winner"].astext.ilike(f"%{winner}%"))

    # Apply supplier filter
    if supplier:
        query = query.filter(
            Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
        )

    return query.all()


def get_awards_by_winner(
    session: Session,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    limit: int = 20,
) -> List[Publication]:
    """
    Get awarded contracts grouped by winner.
    """
    # Base query to get all awarded publications
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply time period filter
    time_filter = get_time_period_filter(year, quarter, month)
    if time_filter:
        query = query.filter(time_filter)

    # Apply sector filter
    if sector_code:
        sector_filter = get_sector_filter(sector_code)
        if sector_filter:
            query = query.join(Publication.cpv_main_code).filter(sector_filter)

    return query.all()


def get_awards_by_supplier(
    session: Session,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    limit: int = 20,
) -> List[Publication]:
    """
    Get awarded contracts grouped by supplier.
    """
    # Base query to get all awarded publications
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply time period filter
    time_filter = get_time_period_filter(year, quarter, month)
    if time_filter:
        query = query.filter(time_filter)

    # Apply sector filter
    if sector_code:
        sector_filter = get_sector_filter(sector_code)
        if sector_filter:
            query = query.join(Publication.cpv_main_code).filter(sector_filter)

    return query.all()


def get_winner_detail(
    session: Session,
    winner_name: str,
    year: Optional[int] = None,
) -> List[Publication]:
    """
    Get detailed information about a specific winner.
    """
    # Get all publications awarded to this winner
    query = session.query(Publication).filter(
        Publication.award.isnot(None),
        Publication.award["winner"].astext.ilike(f"%{winner_name}%"),
    )

    # Apply year filter if provided
    if year:
        query = query.filter(extract("year", Publication.publication_date) == year)

    publications = query.all()
    return publications


def get_supplier_detail(
    session: Session,
    supplier_name: str,
    supplier_id: Optional[str] = None,
    year: Optional[int] = None,
) -> List[Publication]:
    """
    Get detailed information about a specific supplier.
    """
    # Get all publications where this supplier is involved
    query = session.query(Publication).filter(
        Publication.award.isnot(None),
        Publication.award["suppliers"].astext.ilike(f"%{supplier_name}%"),
    )

    # Apply year filter if provided
    if year:
        query = query.filter(extract("year", Publication.publication_date) == year)

    return query.all()


def get_contracts(
    session: Session,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    sector_code: Optional[str] = None,
    winner: Optional[str] = None,
    supplier: Optional[str] = None,
) -> List[Publication]:
    """
    Get a list of awarded contracts with flexible filtering options.
    """
    # Build query for publications with awards
    query = session.query(Publication).filter(Publication.award.isnot(None))

    # Apply time period filter
    time_filter = get_time_period_filter(year, quarter, month)
    if time_filter:
        query = query.filter(time_filter)

    # Apply sector filter
    if sector_code:
        sector_filter = get_sector_filter(sector_code)
        if sector_filter:
            query = query.join(Publication.cpv_main_code).filter(sector_filter)

    # Apply winner filter
    if winner:
        query = query.filter(Publication.award["winner"].astext.ilike(f"%{winner}%"))

    # Apply supplier filter
    if supplier:
        query = query.filter(
            Publication.award["suppliers"].astext.ilike(f"%{supplier}%")
        )

    return query.all()


# Utility functions


def get_time_period_filter(
    year: Optional[int], quarter: Optional[int], month: Optional[int]
):
    """Generate a SQLAlchemy filter based on time period parameters"""
    conditions = []

    if year:
        conditions.append(extract("year", Publication.publication_date) == year)

    if quarter:
        conditions.append(extract("quarter", Publication.publication_date) == quarter)

    if month:
        conditions.append(extract("month", Publication.publication_date) == month)

    return and_(*conditions) if conditions else None


def get_sector_filter(sector_code: Optional[str] = None):
    """Generate a SQLAlchemy filter for CPV sector"""
    if not sector_code:
        return None

    # If only the first two digits are provided (sector level)
    if len(sector_code) == 2:
        return func.substring(CPVCode.code, 1, 2) == sector_code

    # For complete CPV codes
    return CPVCode.code == sector_code


def get_award_value(pub: Publication) -> float:
    """Extract the award value from a publication"""
    if not pub.award:
        return 0

    return pub.award.get("value", 0)
