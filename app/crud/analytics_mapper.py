from datetime import date
from typing import Dict, List, Optional

from app.models.publication_models import Publication
from app.schemas.analytics_schemas import AwardSummary, AwardTimeSeriesItem, AwardSectorItem, RegionItem, WinnerItem, SupplierItem, ContractItem, WinnerDetailResponse, SupplierDetailResponse
from app.util.publication_utils.cpv_codes import get_cpv_sector_code, get_cpv_sector_name
from app.util.publication_utils.nuts_codes import get_nuts_code_as_str
from app.util.publication_utils.publication_converter import PublicationConverter


def map_awards_summary(summary_data: Dict[str, float]) -> AwardSummary:
    """Map summary data to AwardSummary schema"""
    return AwardSummary(
        total_value=summary_data["total_value"],
        total_count=summary_data["total_count"],
        avg_value=summary_data["avg_value"]
    )


def map_timeseries_data(data: List[Dict], period_type: str = "monthly") -> List[AwardTimeSeriesItem]:
    """Organize award data into time periods"""
    periods = {}

    for item in data:
        date_value = item.get("date")
        if not date_value:
            continue

        period_key = format_time_period(period_type, date_value)

        if period_key not in periods:
            periods[period_key] = {"period": period_key, "count": 0, "total_value": 0}

        periods[period_key]["count"] += 1
        periods[period_key]["total_value"] += item.get("value", 0)

    # Convert to list and sort
    result = [AwardTimeSeriesItem(**p) for p in periods.values()]

    # Sort based on period type
    if period_type == "yearly":
        result.sort(key=lambda x: x.period)
    elif period_type == "quarterly":
        result.sort(key=lambda x: (x.period.split("-")[0], x.period.split("-")[1]))
    else:  # monthly
        result.sort(key=lambda x: x.period)

    return result


def map_sector_data(publications: List[Publication], language: str = "nl") -> List[AwardSectorItem]:
    """Process publications into sector data"""
    sector_totals = {}  # For aggregating to sector level

    for pub in publications:
        # Get sector code (first two digits + zeros)
        sector_code = get_cpv_sector_code(pub.cpv_main_code.code)

        # If we don't have this sector yet, add it
        if sector_code not in sector_totals:
            sector_name = get_cpv_sector_name(sector_code, language)
            sector_totals[sector_code] = {
                "sector": sector_name,
                "sector_code": sector_code,
                "count": 0,
                "total_value": 0,
            }

        # Add this publication's data to the sector total
        sector_totals[sector_code]["count"] += 1
        sector_totals[sector_code]["total_value"] += get_award_value(pub)

    # Convert to response items
    sectors = [AwardSectorItem(**data) for data in sector_totals.values()]

    # Sort by total value
    sectors.sort(key=lambda x: x.total_value, reverse=True)

    return sectors


def map_region_data(publications: List[Publication]) -> List[RegionItem]:
    """Process publications into region data"""
    regions = {}
    
    for pub in publications:
        # A publication can have multiple NUTS codes
        for nuts_code in pub.nuts_codes:
            if not nuts_code:
                continue

            # Try to get region name
            region_name = get_nuts_code_as_str(nuts_code)
            if not region_name:
                region_name = f"Region {nuts_code}"  # Fallback if not found

            if nuts_code not in regions:
                regions[nuts_code] = {
                    "region_code": nuts_code,
                    "region_name": region_name,
                    "count": 0,
                    "total_value": 0,
                }

            regions[nuts_code]["count"] += 1
            regions[nuts_code]["total_value"] += get_award_value(pub)

    # Convert to list and sort by total value
    result = [RegionItem(**r) for r in regions.values()]
    result.sort(key=lambda x: x.total_value, reverse=True)

    return result


def map_winner_data(publications: List[Publication], limit: int = 20) -> List[WinnerItem]:
    """Process publications into winner data"""
    winners = {}
    
    for pub in publications:
        winner_name = pub.award.get("winner", "Unknown")

        if winner_name not in winners:
            winners[winner_name] = {"count": 0, "total_value": 0, "sectors": set()}

        winners[winner_name]["count"] += 1
        winners[winner_name]["total_value"] += get_award_value(pub)

        # Add sector information
        sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
        sector_name = get_cpv_sector_name(sector_code, "nl")
        winners[winner_name]["sectors"].add(sector_name)

    # Convert to response format
    result = [
        WinnerItem(
            winner=name,
            count=data["count"],
            total_value=data["total_value"],
            sectors=list(data["sectors"]),
        )
        for name, data in winners.items()
    ]

    # Sort by total value and limit
    result.sort(key=lambda x: x.total_value, reverse=True)
    return result[:limit]


def map_supplier_data(publications: List[Publication], limit: int = 20) -> List[SupplierItem]:
    """Process publications into supplier data"""
    suppliers = {}
    
    for pub in publications:
        # Get suppliers from award data
        supplier_list = get_suppliers_from_award(pub)

        for supplier_data in supplier_list:
            supplier_name = supplier_data.get("name", "Unknown")
            supplier_id = supplier_data.get("id", None)

            # Create a unique key to avoid duplicates
            key = f"{supplier_name}_{supplier_id}" if supplier_id else supplier_name

            if key not in suppliers:
                suppliers[key] = {
                    "supplier_name": supplier_name,
                    "supplier_id": supplier_id,
                    "count": 0,
                    "total_value": 0,
                    "sectors": set(),
                }

            suppliers[key]["count"] += 1
            suppliers[key]["total_value"] += get_award_value(pub)

            # Add sector information
            sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
            sector_name = get_cpv_sector_name(sector_code, "nl")
            suppliers[key]["sectors"].add(sector_name)

    # Convert to response format
    result = [
        SupplierItem(
            supplier_name=data["supplier_name"],
            supplier_id=data["supplier_id"],
            count=data["count"],
            total_value=data["total_value"],
            sectors=list(data["sectors"]),
        )
        for data in suppliers.values()
    ]

    # Sort by total value and limit
    result.sort(key=lambda x: x.total_value, reverse=True)
    return result[:limit]


def map_contract_data(publications: List[Publication]) -> List[ContractItem]:
    """Map publications to ContractItem schema"""
    contracts = []
    
    for pub in publications:
        try:
            contracts.append(ContractItem(
                publication_id=pub.publication_workspace_id,
                title=get_publication_title(pub),
                award_date=pub.publication_date,
                winner=pub.award.get("winner", "Unknown"),
                suppliers=get_suppliers_from_award(pub) or [],
                value=get_award_value(pub),
                sector=get_cpv_sector_name(get_cpv_sector_code(pub.cpv_main_code.code), "nl"),
                cpv_code=pub.cpv_main_code.code,
                buyer=get_buyer_name(pub),
            ))
        except Exception as e:
            # Log error and continue with next publication
            print(f"Error mapping contract data: {e}")
            continue
    
    return contracts


def map_winner_detail(
    publications: List[Publication], 
    winner_name: str, 
    period_type: str = "monthly"
) -> WinnerDetailResponse:
    """Map publications to WinnerDetailResponse schema"""
    if not publications:
        return None
    
    # Calculate summary statistics
    total_value = sum(get_award_value(pub) for pub in publications)
    count = len(publications)
    avg_value = total_value / count if count > 0 else 0

    # Prepare data for time series
    time_data = [
        {"date": pub.publication_date, "value": get_award_value(pub)}
        for pub in publications
    ]

    # Group by sectors
    sectors = {}
    for pub in publications:
        sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
        sector_name = get_cpv_sector_name(sector_code, "nl")

        if sector_code not in sectors:
            sectors[sector_code] = {
                "sector": sector_name,
                "sector_code": sector_code,
                "count": 0,
                "total_value": 0,
            }

        sectors[sector_code]["count"] += 1
        sectors[sector_code]["total_value"] += get_award_value(pub)

    # Map contracts
    contracts = map_contract_data(publications)

    return WinnerDetailResponse(
        winner=winner_name,
        summary=AwardSummary(
            total_value=total_value, 
            total_count=count, 
            avg_value=avg_value
        ),
        time_series=map_timeseries_data(time_data, period_type),
        sectors=[AwardSectorItem(**s) for s in sectors.values()],
        contracts=contracts,
    )


def map_supplier_detail(
    publications: List[Publication], 
    supplier_name: str, 
    supplier_id: Optional[str] = None,
    period_type: str = "monthly"
) -> SupplierDetailResponse:
    """Map publications to SupplierDetailResponse schema"""
    if not publications:
        return None
    
    # Get the most specific supplier ID if available
    specific_supplier_id = supplier_id
    if not specific_supplier_id:
        for pub in publications:
            suppliers = get_suppliers_from_award(pub)
            for supplier in suppliers:
                if supplier_name.lower() in supplier.get("name", "").lower() and supplier.get("id"):
                    specific_supplier_id = supplier.get("id")
                    break
            if specific_supplier_id:
                break

    # Calculate summary statistics
    total_value = sum(get_award_value(pub) for pub in publications)
    count = len(publications)
    avg_value = total_value / count if count > 0 else 0

    # Prepare data for time series
    time_data = [
        {"date": pub.publication_date, "value": get_award_value(pub)}
        for pub in publications
    ]

    # Group by sectors
    sectors = {}
    for pub in publications:
        sector_code = get_cpv_sector_code(pub.cpv_main_code.code)
        sector_name = get_cpv_sector_name(sector_code, "nl")

        if sector_code not in sectors:
            sectors[sector_code] = {
                "sector": sector_name,
                "sector_code": sector_code,
                "count": 0,
                "total_value": 0,
            }

        sectors[sector_code]["count"] += 1
        sectors[sector_code]["total_value"] += get_award_value(pub)

    # Map contracts
    contracts = map_contract_data(publications)

    return SupplierDetailResponse(
        supplier_name=supplier_name,
        supplier_id=specific_supplier_id,
        summary=AwardSummary(
            total_value=total_value, 
            total_count=count, 
            avg_value=avg_value
        ),
        time_series=map_timeseries_data(time_data, period_type),
        sectors=[AwardSectorItem(**s) for s in sectors.values()],
        contracts=contracts,
    )


# Utility functions

def format_time_period(period_type: str, date_value: date) -> str:
    """Format a date into a consistent period string based on period type"""
    year = date_value.year

    if period_type == "yearly":
        return str(year)
    elif period_type == "quarterly":
        quarter = (date_value.month - 1) // 3 + 1
        return f"{year}-Q{quarter}"
    else:  # monthly
        return f"{year}-{date_value.month:02d}"


def get_award_value(pub: Publication) -> float:
    """Extract the award value from a publication"""
    if not pub.award:
        return 0

    return pub.award.get("value", 0)


def get_publication_title(pub: Publication) -> str:
    """Get publication title from dossier titles"""
    if pub.dossier and pub.dossier.titles:
        return PublicationConverter.get_descr_as_str(pub.dossier.titles)
    return "Untitled"


def get_buyer_name(pub: Publication) -> str:
    """Get the buyer (contracting authority) name"""
    if pub.organisation and pub.organisation.organisation_names:
        return PublicationConverter.get_org_name_as_str(
            pub.organisation.organisation_names
        )
    return "Unknown Buyer"


def get_suppliers_from_award(pub: Publication) -> List[Dict[str, str]]:
    """Extract suppliers from publication award data"""
    if not pub.award:
        return []

    # Some awards might have suppliers directly
    if "suppliers" in pub.award and isinstance(pub.award["suppliers"], list):
        return pub.award.get("suppliers", [])

    # Handle case where suppliers is a string or doesn't exist
    return []