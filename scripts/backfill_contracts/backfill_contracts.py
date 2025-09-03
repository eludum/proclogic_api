import argparse
import asyncio
import json
import logging
import os
from datetime import date, datetime
from sys import stdout
from dateutil.relativedelta import relativedelta
from typing import List

import httpx
import numpy as np
from clerk_backend_api import Session
from pydantic import TypeAdapter

import app.crud.publication as crud_publication
from app.ai.recommend import summarize_publication_contract
from app.config.postgres import get_session
from app.config.settings import settings
from app.schemas.publication_schemas import PublicationSchema
from app.util.pubproc import get_notice_xml
from app.util.pubproc_token import get_token
from app.util.web_scraper import scrape_xml_from_procurement_site

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("contract_backfill.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# Rate limiting constants
MAX_REQUESTS_PER_DAY = 24000
REQUEST_DELAY = 2  # seconds
PROGRESS_FILE = "backfill_progress.json"


async def retrieve_publications(
    client: httpx.AsyncClient, dispatch_date_from: date, dispatch_date_to: date
) -> None:
    """
    Main function that retrieves and processes publications.
    """
    progress = load_progress()

    with get_session() as session:
        pubproc_r = await get_timeframe_pubproc_search_data(
            client=client,
            dispatch_date_from=dispatch_date_from,
            dispatch_date_to=dispatch_date_to,
        )
        pubproc_data = TypeAdapter(List[PublicationSchema]).validate_python(pubproc_r)

        logging.info(f"Found {len(pubproc_data)} publications to process")

        # Filter out already processed publications
        processed_ids = set(progress.get("processed_publications", []))
        remaining_pubs = [
            pub
            for pub in pubproc_data
            if pub.publication_workspace_id not in processed_ids
        ]

        logging.info(f"Resuming with {len(remaining_pubs)} unprocessed publications")

        # Check rate limit
        if not check_rate_limit(progress):
            logging.error("Daily rate limit exceeded. Please try again tomorrow.")
            return

        # Process each publication
        for i, pub in enumerate(remaining_pubs):
            try:
                # Check rate limit before each request
                if not check_rate_limit(progress):
                    logging.error("Daily rate limit reached during processing")
                    break

                await process_publication_contract(
                    client=client, pub=pub, session=session
                )

                # Update progress
                progress["processed_publications"].append(pub.publication_workspace_id)
                progress["requests_made"] = progress.get("requests_made", 0) + 1
                save_progress(progress)

                logging.info(
                    f"Processed {i+1}/{len(remaining_pubs)}: {pub.publication_workspace_id}"
                )

                # Add delay between requests
                if i < len(remaining_pubs) - 1:  # Don't delay after the last request
                    await asyncio.sleep(REQUEST_DELAY)

            except Exception as e:
                logging.error(
                    f"Error processing publication {pub.publication_workspace_id}: {e}"
                )
                continue


async def process_publication_contract(
    client: httpx.AsyncClient, pub: PublicationSchema, session: Session
) -> None:
    """
    Process a publication that represents an award.
    """
    xml_content = await get_notice_xml(
        client=client,
        publication_workspace_id=pub.publication_workspace_id,
    )

    if not xml_content:
        logging.info(f"No XML content found via API for publication {pub.publication_workspace_id}")
        
        # Try web scraping as fallback
        xml_content = await scrape_xml_from_procurement_site(pub.publication_workspace_id)
        
        if xml_content:
            logging.info(f"Successfully downloaded XML via web scraping for publication {pub.publication_workspace_id}")
        else:
            logging.warning(f"Failed to get XML content for publication {pub.publication_workspace_id}")

    if xml_content:
        contract = summarize_publication_contract(xml=xml_content)
        if contract:
            pub.contract = contract
            crud_publication.get_or_create_publication(
                publication_schema=pub, session=session
            )
            logging.info(f"Successfully processed contract for publication {pub.publication_workspace_id}")
        else:
            logging.info(f"No contract found in XML for publication {pub.publication_workspace_id}")
    else:
        logging.error(f"No XML content available for publication {pub.publication_workspace_id}")


async def get_timeframe_pubproc_search_data(
    client: httpx.AsyncClient,
    dispatch_date_from: date,
    dispatch_date_to: date,
) -> dict:
    token = get_token()
    page_size = 100

    data = {
        "page": 1,
        "pageSize": page_size,
        "dispatchDateFrom": dispatch_date_from.strftime("%Y-%m-%d"),
        "dispatchDateTo": dispatch_date_to.strftime("%Y-%m-%d"),
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = await client.get(
        settings.pubproc_server + settings.path_sea_api + "/search/publications/byShortLink/v2-z76di6",
        params=data,
        headers=headers,
    )

    r_json = r.json()
    publications = r_json["publicationResultSummary"]["publications"]
    total_count = int(r_json["publicationResultSummary"]["totalCount"])

    if r.status_code == 200:
        pages = int(np.ceil(total_count / page_size))

        if pages > 1:
            for i in range(2, pages + 1):
                data["page"] = i
                r = await client.get(
                    settings.pubproc_server
                    + settings.path_sea_api
                    + "/search/publications/byShortLink/v2-z76di6",
                    params=data,
                    headers=headers,
                )
                await asyncio.sleep(REQUEST_DELAY)
                publications.extend(r.json()["publicationResultSummary"]["publications"])

    return publications


def load_progress() -> dict:
    """Load progress from file if it exists."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                progress = json.load(f)
                # Reset daily counters if it's a new day
                last_date = progress.get("last_reset_date")
                today = datetime.now().strftime("%Y-%m-%d")
                if last_date != today:
                    progress["requests_made"] = 0
                    progress["last_reset_date"] = today
                return progress
        except Exception as e:
            logging.warning(f"Could not load progress file: {e}")

    return {
        "processed_publications": [],
        "requests_made": 0,
        "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
    }


def save_progress(progress: dict) -> None:
    """Save progress to file."""
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        logging.error(f"Could not save progress: {e}")


def check_rate_limit(progress: dict) -> bool:
    """Check if we're within the daily rate limit."""
    requests_made = progress.get("requests_made", 0)
    return requests_made < MAX_REQUESTS_PER_DAY


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Backfill contracts")
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="Reset progress and start from beginning",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.reset_progress and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        logging.info("Progress reset")

    # Start from January 2020
    start_date = date(2020, 1, 1)
    # End at December 2020
    end_date = date(2021, 1, 1)

    logging.info(f"Starting monthly backfill from {start_date} to {end_date}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Loop through each month
        current_date = start_date
        while current_date <= end_date:
            # Calculate the end of the current month
            next_month = current_date + relativedelta(months=1)
            month_end = next_month - relativedelta(days=1)
            
            # Don't go beyond our target end date
            if month_end > end_date:
                month_end = end_date
            
            logging.info(f"Processing month: {current_date} to {month_end}")
            await retrieve_publications(client, current_date, month_end)
            
            # Move to the next month
            current_date = next_month
            
            # Break if we've processed December 2020
            if current_date.year == 2021 and current_date.month == 1:
                break

            logging.info("done")


if __name__ == "__main__":
    asyncio.run(main())
