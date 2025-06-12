#!/usr/bin/env python3
"""
Contract Backfill Script

This script backfills contract data from pubproc API, working backwards from June 10, 2025.
It fetches contracts data, stores XML files locally, and updates the database.

Usage:
    python contract_backfill.py [--start-date YYYY-MM-DD] [--days-back N] [--dry-run]
"""

import asyncio
import argparse
import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config.postgres import get_session
from app.config.settings import Settings
from app.schemas.publication_contract_schemas import ContractSchema
from app.util.pubproc_token import get_token
import app.crud.publication as crud_publication
from app.ai.recommend import extract_data_from_xml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("contract_backfill.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

settings = Settings()


class ContractBackfiller:
    def __init__(
        self, xml_storage_path: str = "data/xml_contracts", requests_per_day: int = 200
    ):
        self.xml_storage_path = Path(xml_storage_path)
        self.xml_storage_path.mkdir(parents=True, exist_ok=True)
        self.requests_per_day = requests_per_day
        self.request_count = 0
        self.contracts_processed = 0
        self.contracts_updated = 0
        self.contracts_failed = 0
        self.contracts_skipped = 0  # Non-award notices
        self.xml_download_failures = 0

    def generate_trace_id(self) -> str:
        """Generate a UUID for BelGov-Trace-Id header"""
        return str(uuid.uuid4())

    async def get_contracts_for_date(
        self, client: httpx.AsyncClient, dispatch_date: date
    ) -> List[dict]:
        """
        Fetch all contracts for a specific dispatch date.
        First request gets the list of contracts using the shortLink.
        """
        if self.request_count >= self.requests_per_day:
            logger.warning(f"Daily request limit of {self.requests_per_day} reached")
            return []

        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "BelGov-Trace-Id": self.generate_trace_id(),
        }

        # Use the specific URL with shortLink as mentioned in requirements
        url = settings.pubproc_server + settings.path_sea_api + "/search/publications"
        params = {
            "shortLink": "mchv4u",  # This filters to contracts only
            "dispatchDateFrom": dispatch_date.strftime("%Y-%m-%d"),
            "dispatchDateTo": dispatch_date.strftime("%Y-%m-%d"),
            "page": 1,
            "pageSize": 100,
        }

        logger.info(f"Fetching contracts for {dispatch_date}")

        try:
            response = await client.get(url, params=params, headers=headers)
            self.request_count += 1

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch contracts for {dispatch_date}: {response.status_code}"
                )
                return []

            data = response.json()
            publications = data.get("publications", [])
            total_count = int(data.get("totalCount", 0))

            logger.info(f"Found {total_count} contracts for {dispatch_date}")

            # Handle pagination if needed
            if total_count > 100:
                pages = (total_count + 99) // 100  # Ceiling division
                for page in range(2, pages + 1):
                    if self.request_count >= self.requests_per_day:
                        logger.warning("Request limit reached during pagination")
                        break

                    params["page"] = page
                    response = await client.get(url, params=params, headers=headers)
                    self.request_count += 1

                    if response.status_code == 200:
                        page_data = response.json()
                        publications.extend(page_data.get("publications", []))
                    else:
                        logger.error(f"Failed to fetch page {page} for {dispatch_date}")

            return publications

        except Exception as e:
            logger.error(f"Error fetching contracts for {dispatch_date}: {e}")
            return []

    async def get_contract_xml(
        self, client: httpx.AsyncClient, publication_workspace_id: str
    ) -> Optional[str]:
        """
        Fetch the XML content for a specific contract.
        This is the second request type mentioned in requirements.
        """
        if self.request_count >= self.requests_per_day:
            logger.warning(f"Daily request limit of {self.requests_per_day} reached")
            return None

        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "BelGov-Trace-Id": self.generate_trace_id(),
        }

        try:
            # Get publication workspace data to extract XML content
            url = (
                settings.pubproc_server
                + settings.path_dos_api
                + f"/publication-workspaces/{publication_workspace_id}"
            )
            response = await client.get(url, headers=headers)
            self.request_count += 1

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch XML for {publication_workspace_id}: {response.status_code}"
                )
                return None

            data = response.json()

            # Extract XML content from the versions
            if "versions" in data and len(data["versions"]) > 0:
                version = data["versions"][0]
                if "notice" in version and "xmlContent" in version["notice"]:
                    return version["notice"]["xmlContent"]

            logger.warning(f"No XML content found for {publication_workspace_id}")
            return None

        except Exception as e:
            logger.error(f"Error fetching XML for {publication_workspace_id}: {e}")
            return None

    def save_xml_locally(
        self, publication_workspace_id: str, xml_content: str, dispatch_date: date
    ) -> bool:
        """Save XML content to local file system"""
        try:
            # Create date-based subdirectory
            date_dir = self.xml_storage_path / dispatch_date.strftime("%Y-%m-%d")
            date_dir.mkdir(exist_ok=True)

            # Save XML file
            xml_file = date_dir / f"{publication_workspace_id}.xml"
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write(xml_content)

            logger.debug(f"Saved XML for {publication_workspace_id} to {xml_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving XML for {publication_workspace_id}: {e}")
            return False

    def parse_contract_data(
        self, publication_data: dict, xml_content: str
    ) -> Optional[ContractSchema]:
        """
        Parse publication and XML data to extract contract information.
        Uses the existing extract_data_from_xml function from the recommend module.
        """
        try:
            # Use the existing extract_data_from_xml function
            contract_schema = extract_data_from_xml(xml_content)

            if contract_schema:
                logger.debug(
                    f"Successfully extracted contract data using extract_data_from_xml"
                )
                return contract_schema
            else:
                logger.warning(
                    "extract_data_from_xml returned None - may not be a contract award notice"
                )
                return None

        except ValueError as e:
            # This is expected for non-award notices (like PriorInformationNotice)
            logger.info(f"Skipping non-award notice: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing contract data: {e}")
            return None

    async def update_publication_with_contract(
        self,
        session: Session,
        publication_workspace_id: str,
        contract_schema: ContractSchema,
        dry_run: bool = False,
    ) -> bool:
        """Update existing publication with contract data"""
        try:
            # Find existing publication
            publication = crud_publication.get_publication_by_workspace_id(
                publication_workspace_id=publication_workspace_id, session=session
            )

            if not publication:
                logger.warning(
                    f"Publication {publication_workspace_id} not found in database"
                )
                return False

            if dry_run:
                logger.info(
                    f"DRY RUN: Would update publication {publication_workspace_id}"
                )
                return True

            # Create or update contract
            contract = crud_publication.get_or_create_contract(
                contract_schema=contract_schema, session=session
            )

            # Link contract to publication
            publication.contract_id = contract.contract_id
            session.commit()

            logger.info(
                f"Updated publication {publication_workspace_id} with contract data"
            )
            return True

        except Exception as e:
            logger.error(f"Error updating publication {publication_workspace_id}: {e}")
            session.rollback()
            return False

    async def process_contracts_for_date(
        self, client: httpx.AsyncClient, dispatch_date: date, dry_run: bool = False
    ):
        """Process all contracts for a specific date"""
        logger.info(f"Processing contracts for {dispatch_date}")

        # Get all contracts for this date
        contracts = await self.get_contracts_for_date(client, dispatch_date)

        if not contracts:
            logger.info(f"No contracts found for {dispatch_date}")
            return

        with get_session() as session:
            for contract_data in contracts:
                if self.request_count >= self.requests_per_day:
                    logger.warning("Daily request limit reached, stopping processing")
                    break

                publication_workspace_id = contract_data.get("publicationWorkspaceId")
                if not publication_workspace_id:
                    logger.warning("Contract missing publicationWorkspaceId")
                    continue

                self.contracts_processed += 1

                # Get XML content
                xml_content = await self.get_contract_xml(
                    client, publication_workspace_id
                )
                if not xml_content:
                    self.xml_download_failures += 1
                    continue

                # Save XML locally
                if not self.save_xml_locally(
                    publication_workspace_id, xml_content, dispatch_date
                ):
                    logger.warning(f"Failed to save XML for {publication_workspace_id}")

                # Parse contract data using the existing XML extraction function
                contract_schema = self.parse_contract_data(contract_data, xml_content)
                if not contract_schema:
                    # This is expected for non-award notices, don't count as failure
                    logger.debug(
                        f"Skipping {publication_workspace_id} - not an award notice or parsing failed"
                    )
                    self.contracts_skipped += 1
                    continue

                # Update database
                if await self.update_publication_with_contract(
                    session, publication_workspace_id, contract_schema, dry_run
                ):
                    self.contracts_updated += 1
                else:
                    self.contracts_failed += 1

                # Add small delay to be respectful to the API
                await asyncio.sleep(0.1)

    async def run_backfill(
        self, start_date: date, days_back: int, dry_run: bool = False
    ):
        """Run the backfill process"""
        logger.info(
            f"Starting contract backfill from {start_date} going {days_back} days back"
        )
        logger.info(f"Request limit: {self.requests_per_day} per day")
        logger.info(f"XML storage path: {self.xml_storage_path}")

        if dry_run:
            logger.info("DRY RUN MODE - No database changes will be made")

        async with httpx.AsyncClient(timeout=60.0) as client:
            current_date = start_date

            for day in range(days_back):
                if self.request_count >= self.requests_per_day:
                    logger.warning("Daily request limit reached, stopping backfill")
                    break

                await self.process_contracts_for_date(client, current_date, dry_run)
                current_date -= timedelta(days=1)

                # Log progress
                logger.info(f"Progress: {day + 1}/{days_back} days processed")
                logger.info(
                    f"Requests used: {self.request_count}/{self.requests_per_day}"
                )
                logger.info(
                    f"Contracts: {self.contracts_processed} processed, {self.contracts_updated} updated, {self.contracts_skipped} skipped, {self.contracts_failed} failed, {self.xml_download_failures} XML failures"
                )

        # Final summary
        logger.info("Backfill completed!")
        logger.info(f"Total requests made: {self.request_count}")
        logger.info(f"Total contracts processed: {self.contracts_processed}")
        logger.info(f"Total contracts updated: {self.contracts_updated}")
        logger.info(f"Total contracts skipped (non-awards): {self.contracts_skipped}")
        logger.info(f"Total contracts failed: {self.contracts_failed}")
        logger.info(f"Total XML download failures: {self.xml_download_failures}")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill contract data from pubproc API"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-06-10",
        help="Start date for backfill (YYYY-MM-DD format, default: 2025-06-10)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Number of days to go back from start date (default: 30)",
    )
    parser.add_argument(
        "--requests-per-day",
        type=int,
        default=200,
        help="Maximum requests per day (default: 200)",
    )
    parser.add_argument(
        "--xml-storage-path",
        type=str,
        default="data/xml_contracts",
        help="Path to store XML files (default: data/xml_contracts)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no database changes)",
    )

    args = parser.parse_args()

    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    except ValueError:
        logger.error("Invalid start date format. Use YYYY-MM-DD")
        return 1

    backfiller = ContractBackfiller(
        xml_storage_path=args.xml_storage_path, requests_per_day=args.requests_per_day
    )

    try:
        asyncio.run(
            backfiller.run_backfill(
                start_date=start_date, days_back=args.days_back, dry_run=args.dry_run
            )
        )
        return 0
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
