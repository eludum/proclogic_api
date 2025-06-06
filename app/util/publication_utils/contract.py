import logging
from typing import Dict, List

from app.models.publication_models import Publication
from app.schemas.publication_contract_schemas import ContractItem
from app.util.publication_utils.cpv_codes import get_cpv_sector_name
from app.util.publication_utils.publication_converter import PublicationConverter


def extract_contract_value(publication: Publication) -> float:
    """Extract contract value from publication's contract data"""
    if not publication.contract:
        return 0.0
    return publication.contract.total_contract_amount or 0.0


def extract_winner_name(publication: Publication) -> str:
    """Extract winner name from publication's contract data"""
    if not publication.contract or not publication.contract.winning_publisher:
        return "Unknown"
    return publication.contract.winning_publisher.name


def extract_buyer_name(publication: Publication) -> str:
    """Extract buyer/contracting authority name"""
    if not publication.contract or not publication.contract.contracting_authority:
        return "Unknown"
    return publication.contract.contracting_authority.name


def extract_suppliers(publication: Publication) -> List[Dict[str, str]]:
    """Extract suppliers from publication contract data"""
    suppliers = []

    if not publication.contract:
        return suppliers

    # Add service provider as a supplier if it exists
    if publication.contract.service_provider:
        suppliers.append(
            {
                "name": publication.contract.service_provider.name,
                "id": publication.contract.service_provider.business_id or "",
            }
        )

    # Note: If you have additional supplier data in other fields,
    # you can add them here

    return suppliers


def get_sector_info(publication: Publication) -> tuple[str, str]:
    """
    Get sector code and name from publication CPV code.

    Returns:
        tuple[str, str]: (sector_code, sector_name)
    """
    if not publication.cpv_main_code:
        return "00000000", "Unknown"

    cpv_code = publication.cpv_main_code.code
    sector_code = cpv_code[:2] + "000000" if len(cpv_code) >= 2 else cpv_code
    sector_name = get_cpv_sector_name(sector_code, "nl")

    return sector_code, sector_name


def get_publication_title(publication: Publication) -> str:
    """Get publication title from dossier titles"""
    if not publication.dossier or not publication.dossier.titles:
        return "Untitled"

    return PublicationConverter.get_descr_as_str(publication.dossier.titles)


def convert_publication_to_contract_item(publication: Publication) -> ContractItem:
    """
    Convert a Publication with contract data to a ContractItem schema.

    Args:
        publication: Publication model instance with contract data

    Returns:
        ContractItem: Pydantic schema for API response

    Raises:
        ValueError: If publication doesn't have contract data
    """
    if not publication.contract:
        raise ValueError(
            f"Publication {publication.publication_workspace_id} has no contract data"
        )

    try:
        # Extract all necessary data
        sector_code, sector_name = get_sector_info(publication)

        contract_item = ContractItem(
            publication_id=publication.publication_workspace_id,
            title=get_publication_title(publication),
            award_date=publication.publication_date,
            winner=extract_winner_name(publication),
            suppliers=extract_suppliers(publication),
            value=extract_contract_value(publication),
            sector=sector_name,
            cpv_code=(
                publication.cpv_main_code.code
                if publication.cpv_main_code
                else "00000000"
            ),
            buyer=extract_buyer_name(publication),
        )

        return contract_item

    except Exception as e:
        logging.error(
            f"Error converting publication {publication.publication_workspace_id} to ContractItem: {e}"
        )
        raise


def convert_publications_to_contract_items(
    publications: List[Publication],
) -> List[ContractItem]:
    """
    Convert a list of Publications to ContractItem schemas.

    Args:
        publications: List of Publication model instances

    Returns:
        List[ContractItem]: List of converted contract items
    """
    contracts = []

    for publication in publications:
        try:
            contract_item = convert_publication_to_contract_item(publication)
            contracts.append(contract_item)
        except Exception as e:
            # Log error but continue processing other contracts
            logging.error(
                f"Skipping publication {publication.publication_workspace_id}: {e}"
            )
            continue

    return contracts


def validate_filters(
    year: int = None,
    quarter: int = None,
    month: int = None,
    page: int = None,
    size: int = None,
) -> Dict[str, str]:
    """
    Validate filter parameters and return any validation errors.

    Returns:
        Dict[str, str]: Dictionary of field names to error messages
    """
    errors = {}

    if year is not None and (year < 1900 or year > 2100):
        errors["year"] = "Year must be between 1900 and 2100"

    if quarter is not None and (quarter < 1 or quarter > 4):
        errors["quarter"] = "Quarter must be between 1 and 4"

    if month is not None and (month < 1 or month > 12):
        errors["month"] = "Month must be between 1 and 12"

    if page is not None and page < 1:
        errors["page"] = "Page must be greater than 0"

    if size is not None and (size < 1 or size > 500):
        errors["size"] = "Size must be between 1 and 500"

    return errors


def format_validation_errors(errors: Dict[str, str]) -> str:
    """Format validation errors into a readable string"""
    if not errors:
        return ""

    error_messages = [f"{field}: {message}" for field, message in errors.items()]
    return "; ".join(error_messages)
