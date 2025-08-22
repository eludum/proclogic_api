#!/usr/bin/env python3
"""
Enhanced Contract Backfill Script

This script backfills contract data from pubproc API with enhanced progress tracking and state management.
It automatically resumes from where it left off if interrupted, with proper checkpointing.

Features:
- Automatic progress checkpointing to JSON file
- Resume from last checkpoint on restart
- Rate limiting with automatic sleep until midnight
- XML storage with organized directory structure
- Comprehensive logging and statistics
- Dry-run mode for testing
- Graceful interrupt handling

Usage:
    python backfill_contracts.py [options]

Examples:
    # Process a whole year
    python backfill_contracts.py --year 2024

    # Process a year with dry run
    python backfill_contracts.py --year 2023 --dry-run

    # Resume from checkpoint
    python backfill_contracts.py --year 2024 --resume

    # Use custom storage path
    python backfill_contracts.py --year 2024 --xml-storage-path /custom/path
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

import proclogic_api.app.crud.publication as crud_publication
from proclogic_api.app.ai.recommend import summarize_publication_contract
from proclogic_api.app.config.postgres import get_session
from proclogic_api.app.config.settings import Settings
from proclogic_api.app.models.publication_models import Publication
from proclogic_api.app.schemas.publication_contract_schemas import \
    ContractSchema
from proclogic_api.app.util.pubproc_token import get_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("contract_backfill.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

settings = Settings()


def calculate_days_in_year(year: int) -> int:
    """Calculate the number of days in a given year (handles leap years)"""
    start_of_year = date(year, 1, 1)
    start_of_next_year = date(year + 1, 1, 1)
    return (start_of_next_year - start_of_year).days


class ProgressTracker:
    """Handles progress tracking and checkpointing"""

    def __init__(self, checkpoint_file: str = "backfill_progress.json"):
        self.checkpoint_file = Path(checkpoint_file)
        self.data = self._load_checkpoint()

    def _load_checkpoint(self) -> Dict[str, Any]:
        """Load checkpoint data from file"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r") as f:
                    data = json.load(f)
                    logger.info(f"Loaded checkpoint from {self.checkpoint_file}")
                    return data
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")

        return {
            "current_date": None,
            "start_date": None,
            "end_date": None,
            "days_remaining": 0,
            "processed_dates": [],
            "stats": {
                "contracts_processed": 0,
                "contracts_updated": 0,
                "contracts_failed": 0,
                "contracts_skipped": 0,
                "xml_download_failures": 0,
                "total_requests": 0,
            },
            "last_update": None,
        }

    def save_checkpoint(self):
        """Save current progress to checkpoint file"""
        try:
            self.data["last_update"] = datetime.now().isoformat()
            with open(self.checkpoint_file, "w") as f:
                json.dump(self.data, f, indent=2)
            logger.debug(f"Checkpoint saved to {self.checkpoint_file}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def update_stats(self, **kwargs):
        """Update statistics"""
        for key, value in kwargs.items():
            if key in self.data["stats"]:
                self.data["stats"][key] += value

    def mark_date_processed(self, date_obj: date):
        """Mark a date as processed"""
        date_str = date_obj.isoformat()
        if date_str not in self.data["processed_dates"]:
            self.data["processed_dates"].append(date_str)

    def is_date_processed(self, date_obj: date) -> bool:
        """Check if a date has been processed"""
        return date_obj.isoformat() in self.data["processed_dates"]

    def set_date_range(self, start_date: date, end_date: date):
        """Set the date range for processing"""
        self.data["start_date"] = start_date.isoformat()
        self.data["end_date"] = end_date.isoformat()
        delta = start_date - end_date
        self.data["days_remaining"] = delta.days + 1

    def update_current_date(self, current_date: date):
        """Update the current processing date"""
        self.data["current_date"] = current_date.isoformat()

    def get_resume_date(self) -> Optional[date]:
        """Get the date to resume from"""
        if self.data["current_date"]:
            return date.fromisoformat(self.data["current_date"])
        return None

    def clear_checkpoint(self):
        """Clear checkpoint file"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            logger.info("Checkpoint file cleared")


class ContractBackfiller:
    def __init__(
        self,
        xml_storage_path: str = "data/xml_contracts",
        requests_per_day: int = 24000,
        checkpoint_file: str = "backfill_progress.json",
    ):
        self.xml_storage_path = Path(xml_storage_path)
        self.xml_storage_path.mkdir(parents=True, exist_ok=True)
        self.requests_per_day = requests_per_day
        self.request_count = 0
        self.daily_reset_time = None
        self.progress = ProgressTracker(checkpoint_file)
        self.interrupted = False

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        logger.info(
            f"Received signal {signum}. Saving progress and shutting down gracefully..."
        )
        self.interrupted = True
        self.progress.save_checkpoint()
        sys.exit(0)

    def generate_trace_id(self) -> str:
        """Generate a UUID for BelGov-Trace-Id header"""
        return str(uuid.uuid4())

    def reset_daily_counter_if_needed(self):
        """Reset the request counter if it's a new day"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self.daily_reset_time is None or self.daily_reset_time < today_start:
            if self.daily_reset_time is not None:
                logger.info(
                    f"New day started. Reset request counter. Total requests made yesterday: {self.request_count}"
                )
            self.request_count = 0
            self.daily_reset_time = today_start

    async def sleep_until_midnight(self):
        """Sleep until midnight to reset the daily rate limit"""
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=1
        )
        sleep_time = (tomorrow - now).total_seconds()

        logger.info(
            f"Daily request limit ({self.requests_per_day}) reached. Sleeping until midnight..."
        )
        logger.info(
            f"Will resume at {tomorrow.strftime('%Y-%m-%d %H:%M:%S')} (in {sleep_time/3600:.1f} hours)"
        )

        # Save progress before sleeping
        self.progress.save_checkpoint()

        await asyncio.sleep(sleep_time)
        logger.info("Resuming after midnight. Request counter reset.")

    async def check_and_handle_rate_limit(self):
        """Check if we've hit the rate limit and sleep if needed"""
        self.reset_daily_counter_if_needed()

        if self.request_count >= self.requests_per_day:
            await self.sleep_until_midnight()

    async def get_contracts_for_date(
        self,
        client: httpx.AsyncClient,
        dispatch_date_from: date,
        dispatch_date_to: date,
    ) -> List[dict]:
        """Fetch all contracts for a specific dispatch date"""
        await self.check_and_handle_rate_limit()

        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "BelGov-Trace-Id": self.generate_trace_id(),
        }

        url = settings.pubproc_server + settings.path_sea_api + "/search/publications"
        params = {
            "shortLink": "mchv4u",  # Filter to contracts only
            "dispatchDateFrom": dispatch_date_from.strftime("%Y-%m-%d"),
            "dispatchDateTo": dispatch_date_to.strftime("%Y-%m-%d"),
            "page": 1,
            "pageSize": 100,
        }

        logger.info(f"Fetching contracts for {dispatch_date_from}")

        try:
            response = await client.get(url, params=params, headers=headers)
            self.request_count += 1
            self.progress.update_stats(total_requests=1)

            # Add delay to respect rate limits
            await asyncio.sleep(5)

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch contracts for {dispatch_date_from}: {response.status_code}"
                )
                return []

            data = response.json()
            publications = data.get("publications", [])
            total_count = int(data.get("totalCount", 0))

            logger.info(f"Found {total_count} contracts for {dispatch_date_from}")

            # Handle pagination if needed
            if total_count > 100:
                pages = (total_count + 99) // 100
                for page in range(2, pages + 1):
                    if self.interrupted:
                        break

                    await self.check_and_handle_rate_limit()

                    params["page"] = page
                    response = await client.get(url, params=params, headers=headers)
                    self.request_count += 1
                    self.progress.update_stats(total_requests=1)

                    await asyncio.sleep(5)

                    if response.status_code == 200:
                        page_data = response.json()
                        publications.extend(page_data.get("publications", []))
                    else:
                        logger.error(
                            f"Failed to fetch page {page} for {dispatch_date_from}"
                        )

            return publications

        except Exception as e:
            logger.error(f"Error fetching contracts for {dispatch_date_from}: {e}")
            return []

    async def get_contract_xml(
        self, client: httpx.AsyncClient, publication_workspace_id: str
    ) -> Optional[str]:
        """Fetch the XML content for a specific contract"""
        await self.check_and_handle_rate_limit()

        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "BelGov-Trace-Id": self.generate_trace_id(),
        }

        try:
            url = (
                settings.pubproc_server
                + settings.path_dos_api
                + f"/publication-workspaces/{publication_workspace_id}"
            )
            response = await client.get(url, headers=headers)
            self.request_count += 1
            self.progress.update_stats(total_requests=1)

            await asyncio.sleep(5)

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch XML for {publication_workspace_id}: {response.status_code}"
                )
                return None

            data = response.json()

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
        """Save XML content to local file system with organized structure"""
        try:
            # Create year/month subdirectory structure
            date_dir = (
                self.xml_storage_path
                / dispatch_date.strftime("%Y")
                / dispatch_date.strftime("%m")
            )
            date_dir.mkdir(parents=True, exist_ok=True)

            # Save XML file with day-month-year_publicationId.xml format
            xml_file = (
                date_dir
                / f"{dispatch_date.strftime('%d-%m-%Y')}_{publication_workspace_id}.xml"
            )
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
        """Parse publication and XML data to extract contract information"""
        try:
            contract_schema = summarize_publication_contract(xml=xml_content)

            if contract_schema:
                logger.debug(
                    "Successfully extracted contract data using summarize_publication_contract"
                )
                
                return contract_schema
            else:
                logger.debug(
                    "summarize_publication_contract returned None - may not be a contract award notice"
                )
                return None

        except ValueError as e:
            logger.debug(f"Skipping non-award notice: {e}")
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
            publication = session.get(Publication, publication_workspace_id)

            if not publication:
                logger.error(f"Publication {publication_workspace_id} not found")
                return False

            if dry_run:
                logger.info(
                    f"DRY RUN: Would update publication {publication_workspace_id} with contract"
                )
                return True

            # Create the contract using the existing create_contract function
            contract = crud_publication.create_contract(contract_schema, session)

            # Link contract to publication
            publication.contract = contract

            session.add(publication)
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
        self,
        client: httpx.AsyncClient,
        dispatch_date_from: date,
        dispatch_date_to: date,
        dry_run: bool = False,
    ):
        """Process all contracts for a specific date"""
        if self.progress.is_date_processed(dispatch_date_from):
            logger.info(f"Date {dispatch_date_from} already processed, skipping")
            return

        logger.info(f"Processing contracts for {dispatch_date_from}")

        # Get all contracts for this date
        contracts = await self.get_contracts_for_date(
            client, dispatch_date_from, dispatch_date_to
        )

        if not contracts:
            logger.info(f"No contracts found for {dispatch_date_from}")
            self.progress.mark_date_processed(dispatch_date_from)
            self.progress.save_checkpoint()
            return

        date_stats = {
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "skipped": 0,
            "xml_failures": 0,
        }

        for contract_data in contracts:
            if self.interrupted:
                logger.info("Processing interrupted by user")
                break

            publication_workspace_id = contract_data.get("publicationWorkspaceId")
            if not publication_workspace_id:
                logger.warning("Contract missing publicationWorkspaceId")
                continue

            date_stats["processed"] += 1

            # Get XML content
            xml_content = await self.get_contract_xml(client, publication_workspace_id)
            if not xml_content:
                date_stats["xml_failures"] += 1
                continue

            # Save XML locally
            if not self.save_xml_locally(
                publication_workspace_id, xml_content, dispatch_date_from
            ):
                logger.warning(f"Failed to save XML for {publication_workspace_id}")

            # Parse contract data
            contract_schema = self.parse_contract_data(contract_data, xml_content)
            if not contract_schema:
                date_stats["skipped"] += 1
                continue

            # Update database
            with get_session() as session:
                if await self.update_publication_with_contract(
                    session, publication_workspace_id, contract_schema, dry_run
                ):
                    date_stats["updated"] += 1
                else:
                    date_stats["failed"] += 1

        # Update overall stats
        self.progress.update_stats(
            contracts_processed=date_stats["processed"],
            contracts_updated=date_stats["updated"],
            contracts_failed=date_stats["failed"],
            contracts_skipped=date_stats["skipped"],
            xml_download_failures=date_stats["xml_failures"],
        )

        # Mark date as processed
        self.progress.mark_date_processed(dispatch_date_from)
        self.progress.save_checkpoint()

        logger.info(f"Date {dispatch_date_from} completed: {date_stats}")

    def print_summary(self):
        """Print final summary"""
        stats = self.progress.data["stats"]
        logger.info("=" * 60)
        logger.info("BACKFILL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total contracts processed: {stats['contracts_processed']}")
        logger.info(f"Total contracts updated: {stats['contracts_updated']}")
        logger.info(
            f"Total contracts skipped (non-awards): {stats['contracts_skipped']}"
        )
        logger.info(f"Total contracts failed: {stats['contracts_failed']}")
        logger.info(f"Total XML download failures: {stats['xml_download_failures']}")
        logger.info(f"Total API requests made: {stats['total_requests']}")
        logger.info(f"Dates processed: {len(self.progress.data['processed_dates'])}")
        logger.info("=" * 60)

    async def run_backfill(
        self,
        start_date: date,
        days_back: int,
        dry_run: bool = False,
        resume: bool = False,
    ):
        """Run the backfill process with optional resume capability"""
        end_date = start_date - timedelta(days=days_back - 1)

        if resume and self.progress.get_resume_date():
            resume_date = self.progress.get_resume_date()
            logger.info(f"Resuming backfill from checkpoint at date: {resume_date}")
            current_date = resume_date
        else:
            logger.info(
                f"Starting contract backfill from {start_date} going {days_back} days back"
            )
            self.progress.set_date_range(start_date, end_date)
            current_date = start_date

        logger.info(f"Request limit: {self.requests_per_day} per day")
        logger.info(f"XML storage path: {self.xml_storage_path}")

        if dry_run:
            logger.info("DRY RUN MODE - No database changes will be made")

        self.reset_daily_counter_if_needed()

        async with httpx.AsyncClient(timeout=60.0) as client:
            while current_date >= end_date and not self.interrupted:
                self.progress.update_current_date(current_date)

                await self.process_contracts_for_date(client, current_date, dry_run)

                current_date -= timedelta(days=1)

                # Log progress every few dates
                days_completed = (start_date - current_date).days
                if days_completed % 5 == 0 or current_date < end_date:
                    logger.info(
                        f"Progress: {days_completed}/{days_back} days processed"
                    )
                    logger.info(
                        f"Requests used today: {self.request_count}/{self.requests_per_day}"
                    )
                    stats = self.progress.data["stats"]
                    logger.info(
                        f"Stats: {stats['contracts_processed']} processed, "
                        f"{stats['contracts_updated']} updated, "
                        f"{stats['contracts_skipped']} skipped, "
                        f"{stats['contracts_failed']} failed"
                    )

        if not self.interrupted:
            logger.info("Backfill completed successfully!")
            self.progress.clear_checkpoint()

        self.print_summary()


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Contract Backfill Script with progress tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year to process (e.g., 2024)",
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
        "--checkpoint-file",
        type=str,
        default="backfill_progress.json",
        help="Checkpoint file for progress tracking (default: backfill_progress.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no database changes)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--clear-checkpoint",
        action="store_true",
        help="Clear existing checkpoint and start fresh",
    )

    args = parser.parse_args()

    # Handle checkpoint clearing
    if args.clear_checkpoint:
        checkpoint_path = Path(args.checkpoint_file)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info(f"Cleared checkpoint file: {args.checkpoint_file}")
        else:
            logger.info("No checkpoint file to clear")
        return 0

    # Set start_date to end of year, calculate days_back for whole year
    start_date = date(args.year, 12, 31)
    days_back = calculate_days_in_year(args.year)
    logger.info(f"Processing whole year {args.year} ({days_back} days)")

    backfiller = ContractBackfiller(
        xml_storage_path=args.xml_storage_path,
        requests_per_day=args.requests_per_day,
        checkpoint_file=args.checkpoint_file,
    )

    try:
        asyncio.run(
            backfiller.run_backfill(
                start_date=start_date,
                days_back=days_back,
                dry_run=args.dry_run,
                resume=args.resume,
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
