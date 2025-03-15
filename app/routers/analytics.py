from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func

from app.config.postgres import get_session
from app.models.publication_models import Publication, CPVCode
from app.schemas.publication_schemas import PublicationSchema
from app.util.clerk import AuthUser, get_auth_user
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.publication_utils.cpv_codes import get_cpv_sector_and_description

analytics_router = APIRouter()

class AwardSummary:
    """Helper class for award data processing"""
    @staticmethod
    def process_award_data(publications: List[PublicationSchema]) -> List[Dict]:
        """Process award data from publications for analytics"""
        awards_data = []
        for pub in publications:
            if pub.award:
                award_data = {
                    "publication_id": pub.publication_workspace_id,
                    "publication_date": pub.publication_date,
                    "sector": get_cpv_sector_and_description(pub.cpv_main_code.code, "nl"),
                    "cpv_code": pub.cpv_main_code.code,
                    "winner": pub.award.get("winner", "Unknown"),
                    "organisation": PublicationConverter.get_org_name_as_str(pub.organisation.organisation_names),
                    "value": pub.award.get("value", 0),
                }
            
                awards_data.append(award_data)
        
        return awards_data


@analytics_router.get("/analytics/total-value")
async def get_awards_total_value(
    auth_user: AuthUser = Depends(get_auth_user),
    year: Optional[int] = Query(None, description="Filter by year"),
    quarter: Optional[int] = Query(None, description="Filter by quarter (1-4)"),
    sector: Optional[str] = Query(None, description="Filter by sector (first two digits of CPV)"),
):
    """Get total monetary value of all awarded contracts with optional filters"""
    with get_session() as session:
        query = session.query(func.sum(Publication.estimated_value)) \
            .filter(Publication.award.isnot(None))
        
        # Apply filters
        if year:
            query = query.filter(func.extract('year', Publication.publication_date) == year)
        
        if quarter:
            query = query.filter(func.extract('quarter', Publication.publication_date) == quarter)
            
        if sector:
            # Filter by first two digits of CPV code
            query = query.join(Publication.cpv_main_code) \
                .filter(func.substring(CPVCode.code, 1, 2) == sector[:2])
        
        result = query.scalar() or 0
        
        return {"total_value": result}


@analytics_router.get("/analytics/by-sector")
async def get_awards_by_sector(
    auth_user: AuthUser = Depends(get_auth_user),
    year: Optional[int] = Query(None, description="Filter by year"),
):
    """Get award counts and total values grouped by sector"""
    with get_session() as session:
        # Get all awarded publications
        query = session.query(Publication) \
            .filter(Publication.award.isnot(None))
        
        # Apply year filter if provided
        if year:
            query = query.filter(func.extract('year', Publication.publication_date) == year)
            
        publications = query.all()
        
        # Process and group by sector
        awards_data = AwardSummary.process_award_data(publications)
        
        # Group by sector
        sectors = {}
        for award in awards_data:
            sector = award["sector"]
            if sector not in sectors:
                sectors[sector] = {
                    "count": 0,
                    "total_value": 0
                }
            
            sectors[sector]["count"] += 1
            sectors[sector]["total_value"] += award["value"]
        
        # Convert to list for output
        result = [
            {
                "sector": sector,
                "count": data["count"],
                "total_value": data["total_value"]
            }
            for sector, data in sectors.items()
        ]
        
        # Sort by total value
        result.sort(key=lambda x: x["total_value"], reverse=True)
        
        return result


@analytics_router.get("/analytics/by-winner")
async def get_awards_by_winner(
    auth_user: AuthUser = Depends(get_auth_user),
    limit: int = Query(10, description="Limit number of winners returned"),
    year: Optional[int] = Query(None, description="Filter by year"),
):
    """Get top winning companies by award count and value"""
    with get_session() as session:
        # Get all awarded publications
        query = session.query(Publication) \
            .filter(Publication.award.isnot(None))
        
        # Apply year filter if provided
        if year:
            query = query.filter(func.extract('year', Publication.publication_date) == year)
            
        publications = query.all()
        
        # Process and group by winner
        awards_data = AwardSummary.process_award_data(publications)
        
        # Group by winner
        winners = {}
        for award in awards_data:
            winner = award["winner"]
            if winner not in winners:
                winners[winner] = {
                    "count": 0,
                    "total_value": 0,
                    "sectors": set()
                }
            
            winners[winner]["count"] += 1
            winners[winner]["total_value"] += award["value"]
            winners[winner]["sectors"].add(award["sector"])
        
        # Convert to list for output
        result = [
            {
                "winner": winner,
                "count": data["count"],
                "total_value": data["total_value"],
                "sectors": list(data["sectors"])
            }
            for winner, data in winners.items()
        ]
        
        # Sort by total value and limit
        result.sort(key=lambda x: x["total_value"], reverse=True)
        result = result[:limit]
        
        return result


@analytics_router.get("/analytics/by-organisation")
async def get_awards_by_organisation(
    auth_user: AuthUser = Depends(get_auth_user),
    limit: int = Query(10, description="Limit number of organisations returned"),
    year: Optional[int] = Query(None, description="Filter by year"),
):
    """Get top organisations by award count and total value"""
    with get_session() as session:
        # Get all awarded publications
        query = session.query(Publication) \
            .filter(Publication.award.isnot(None))
        
        # Apply year filter if provided
        if year:
            query = query.filter(func.extract('year', Publication.publication_date) == year)
            
        publications = query.all()
        
        # Process and group by organisation
        awards_data = AwardSummary.process_award_data(publications)
        
        # Group by organisation
        organisations = {}
        for award in awards_data:
            org = award["organisation"]
            if not org:
                org = "Unknown"
                
            if org not in organisations:
                organisations[org] = {
                    "count": 0,
                    "total_value": 0
                }
            
            organisations[org]["count"] += 1
            organisations[org]["total_value"] += award["value"]
        
        # Convert to list for output
        result = [
            {
                "organisation": org,
                "count": data["count"],
                "total_value": data["total_value"]
            }
            for org, data in organisations.items()
        ]
        
        # Sort by total value and limit
        result.sort(key=lambda x: x["total_value"], reverse=True)
        result = result[:limit]
        
        return result


@analytics_router.get("/analytics/time-series")
async def get_awards_time_series(
    auth_user: AuthUser = Depends(get_auth_user),
    timeframe: str = Query("monthly", description="Time grouping: monthly, quarterly, or yearly"),
    years: Optional[List[int]] = Query(None, description="List of years to include"),
):
    """Get award counts and values over time"""
    with get_session() as session:
        # Get all awarded publications
        query = session.query(Publication) \
            .filter(Publication.award.isnot(None))
        
        # Apply years filter if provided
        if years:
            query = query.filter(func.extract('year', Publication.publication_date).in_(years))
            
        publications = query.all()
        
        # Process publications
        awards_data = AwardSummary.process_award_data(publications)
        
        # Group by time period
        time_periods = {}
        
        for award in awards_data:
            date = award["publication_date"]
            year = date.year
            
            if timeframe == "yearly":
                period_key = str(year)
            elif timeframe == "quarterly":
                quarter = (date.month - 1) // 3 + 1
                period_key = f"{year}-Q{quarter}"
            else:  # monthly
                period_key = f"{year}-{date.month:02d}"
                
            if period_key not in time_periods:
                time_periods[period_key] = {
                    "period": period_key,
                    "count": 0,
                    "total_value": 0
                }
            
            time_periods[period_key]["count"] += 1
            time_periods[period_key]["total_value"] += award["value"]
        
        # Convert to list and sort chronologically
        result = list(time_periods.values())
        
        # Sort based on timeframe
        if timeframe == "yearly":
            result.sort(key=lambda x: x["period"])
        elif timeframe == "quarterly":
            result.sort(key=lambda x: (x["period"].split("-")[0], x["period"].split("-")[1]))
        else:  # monthly
            result.sort(key=lambda x: x["period"])
        
        return result


@analytics_router.get("/analytics/value-ranges")
async def get_awards_by_value_range(
    auth_user: AuthUser = Depends(get_auth_user),
    year: Optional[int] = Query(None, description="Filter by year"),
):
    """Get award counts by value ranges"""
    with get_session() as session:
        # Get all awarded publications
        query = session.query(Publication) \
            .filter(Publication.award.isnot(None))
        
        # Apply year filter if provided
        if year:
            query = query.filter(func.extract('year', Publication.publication_date) == year)
            
        publications = query.all()
        
        # Process publications
        awards_data = AwardSummary.process_award_data(publications)
        
        # Define value ranges (in euros)
        ranges = [
            {"min": 0, "max": 10000, "label": "< €10,000"},
            {"min": 10000, "max": 50000, "label": "€10,000 - €50,000"},
            {"min": 50000, "max": 100000, "label": "€50,000 - €100,000"},
            {"min": 100000, "max": 500000, "label": "€100,000 - €500,000"},
            {"min": 500000, "max": 1000000, "label": "€500,000 - €1,000,000"},
            {"min": 1000000, "max": 5000000, "label": "€1,000,000 - €5,000,000"},
            {"min": 5000000, "max": float('inf'), "label": "> €5,000,000"}
        ]
        
        # Count awards in each range
        for r in ranges:
            r["count"] = 0
            r["total_value"] = 0
        
        for award in awards_data:
            value = award["value"]
            for r in ranges:
                if r["min"] <= value < r["max"]:
                    r["count"] += 1
                    r["total_value"] += value
                    break
        
        return ranges


@analytics_router.get("/analytics/detail/{publication_workspace_id}")
async def get_award_detail(
    publication_workspace_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get detailed information about a specific award"""
    with get_session() as session:
        publication = session.query(Publication) \
            .filter(Publication.publication_workspace_id == publication_workspace_id) \
            .filter(Publication.award.isnot(None)) \
            .first()
        
        if not publication:
            raise HTTPException(status_code=404, detail="Award not found")
        
        # Process award data
        result = {
            "publication_id": publication.publication_workspace_id,
            "publication_date": publication.publication_date,
            "dispatch_date": publication.dispatch_date,
            "sector": get_cpv_sector_and_description(publication.cpv_main_code.code, "nl"),
            "cpv_code": publication.cpv_main_code.code,
            "award": publication.award,
        }
        
        # Get dossier information
        if publication.dossier:
            result["dossier"] = {
                "reference_number": publication.dossier.reference_number,
                "title": PublicationConverter.get_descr_as_str(publication.dossier.titles),
                "description": PublicationConverter.get_descr_as_str(publication.dossier.descriptions),
            }
        
        # Get organisation information
        if publication.organisation and publication.organisation.organisation_names:
            org_names = {}
            for org_name in publication.organisation.organisation_names:
                org_names[org_name.language] = org_name.text
            
            result["organisation"] = {
                "id": publication.organisation.organisation_id,
                "names": org_names
            }
        
        return result
