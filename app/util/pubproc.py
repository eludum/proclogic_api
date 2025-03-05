import asyncio
import logging
import uuid
import zipfile
from datetime import date, timedelta
from io import BytesIO
from typing import List

import httpx
import numpy as np
import pycron
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.ai.recommend import (
    get_recommendation,
    summarize_publication_award,
    summarize_publication_with_files,
    summarize_publication_without_files,
)
from app.config.postgres import get_session
from app.config.settings import Settings
from app.schemas.company_schemas import CompanyPublicationMatchSchema
from app.schemas.publication_schemas import CPVCodeSchema, PublicationSchema
from app.util.pubproc_token import get_token
from app.util.redis_cache import invalidate_publication_cache, redis_cache

settings = Settings()


async def fetch_pubproc_data() -> None:
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await retrieve_publications(client=client)
            await asyncio.sleep(600)  # 10 minutes in seconds
        except Exception as e:
            logging.error("error in fetching data: %s", e)
            await asyncio.sleep(600)  # wait a minute before retrying
        # TODO: remove continue in prod
        continue

        if pycron.is_now("*/15 6-19 * * 1-5"):
            try:
                async with httpx.AsyncClient() as client:
                    await retrieve_publications(client=client)
                await asyncio.sleep(600)  # 10 minutes in seconds
            except Exception as e:
                logging.error("error in fetching data: %s", e)
        await asyncio.sleep(60)


async def retrieve_publications(client: httpx.AsyncClient) -> None:
    """
    Main function that retrieves and processes publications.
    """
    with get_session() as session:
        pubproc_r = await get_daily_pubproc_search_data(client=client)
        pubproc_data = TypeAdapter(List[PublicationSchema]).validate_python(pubproc_r)

        # Process each publication
        for pub in pubproc_data:
            print(f"Processing publication {pub.publication_workspace_id}")
            try:
                await process_publication(client, pub, session)
            except Exception as e:
                logging.error(
                    f"Error processing publication {pub.publication_workspace_id}: {e}"
                )


async def process_publication(
    client: httpx.AsyncClient, pub: PublicationSchema, session: Session
) -> None:
    """
    Process an individual publication by checking if it exists and handling it accordingly.
    """
    # Get documents
    filesmap = await get_publication_workspace_documents(
        client=client, publication_workspace_id=pub.publication_workspace_id
    )

    # Check if the publication already exists
    existing_publication = crud_publication.publication_exists(
        publication_workspace_id=pub.publication_workspace_id, session=session
    )

    if existing_publication and pub.vault_submission_deadline is not None:
        await update_existing_publication(
            client=client, pub=pub, filesmap=filesmap, session=session
        )
    elif not existing_publication and pub.vault_submission_deadline is not None:
        await create_new_publication(
            client=client, pub=pub, filesmap=filesmap, session=session
        )
    elif pub.vault_submission_deadline is None:
        await process_award_publication(client=client, pub=pub, session=session)


async def update_existing_publication(
    client: httpx.AsyncClient, pub: PublicationSchema, filesmap: dict, session: Session
) -> None:
    """
    Update an existing publication with new information if necessary.
    """
    if is_new_notice_version_available(
        incoming_notice_ids=pub.notice_ids,
        publication_workspace_id=pub.publication_workspace_id,
    ):
        invalidate_publication_cache(pub.publication_workspace_id)

        # Get fresh data
        xml_content = await get_notice_xml(
            client=client,
            publication_workspace_id=pub.publication_workspace_id,
        )

        await enrich_publication_with_ai(
            pub=pub, xml_content=xml_content, filesmap=filesmap
        )

        # First update the publication
        crud_publication.get_or_create_publication(
            publication_schema=pub, session=session
        )

        # Then generate (new) recommendations
        await generate_company_recommendations(pub=pub, session=session)


async def create_new_publication(
    client: httpx.AsyncClient, pub: PublicationSchema, filesmap: dict, session: Session
) -> None:
    """
    Create a new publication and generate recommendations for companies.
    """
    xml_content = await get_notice_xml(
        client=client, publication_workspace_id=pub.publication_workspace_id
    )

    # Add AI-generated content
    await enrich_publication_with_ai(
        pub=pub, xml_content=xml_content, filesmap=filesmap
    )

    # First create the publication
    crud_publication.get_or_create_publication(publication_schema=pub, session=session)

    # Then generate recommendations
    await generate_company_recommendations(pub=pub, session=session)


async def process_award_publication(
    client: httpx.AsyncClient, pub: PublicationSchema, session: Session
) -> None:
    """
    Process a publication that represents an award.
    """
    xml_content = await get_notice_xml(
        client=client,
        publication_workspace_id=pub.publication_workspace_id,
    )

    # Get award information
    pub.award = summarize_publication_award(xml=xml_content)

    # Save to database
    crud_publication.get_or_create_publication(publication_schema=pub, session=session)


async def enrich_publication_with_ai(
    pub: PublicationSchema, xml_content: str, filesmap: dict
) -> None:
    """
    Enrich a publication with AI-generated content.
    """
    if filesmap:
        try:
            estimated_value, summary, citations = summarize_publication_with_files(
                publication=pub, xml=xml_content, filesmap=filesmap
            )
            pub.ai_summary_with_documents = summary + citations
            pub.estimated_value = float(estimated_value)
        except Exception as e:
            logging.error(f"Error in summarize_publication_with_files: {e}")
            pub.ai_summary_with_documents = "Error processing documents."
    else:
        try:
            pub.ai_summary_without_documents = summarize_publication_without_files(
                publication=pub, xml=xml_content
            )
        except Exception as e:
            logging.error(f"Error in summarize_publication_without_files: {e}")
            pub.ai_summary_without_documents = "Error generating summary."


async def generate_company_recommendations(
    pub: PublicationSchema, session: Session
) -> None:
    """
    Generate company recommendations for a publication.
    """
    match_schemas = []

    # Process each company
    for company in crud_company.get_all_companies(session=session):
        try:
            match, match_percentage = get_recommendation(
                publication=pub, company=company
            )

            if match:
                # Create match record
                match_schema = CompanyPublicationMatchSchema(
                    company_vat_number=company.vat_number,
                    publication_workspace_id=pub.publication_workspace_id,
                    match_percentage=float(match_percentage),
                    is_recommended=True,
                    is_saved=False,
                    is_viewed=False,
                )
                match_schemas.append(match_schema)
        except Exception as e:
            logging.error(
                f"Error generating recommendation for company {company.vat_number}: {e}"
            )

    # If we have matches, update the publication
    if match_schemas:
        crud_publication.get_or_create_publication(
            publication_schema=pub, session=session
        )


async def get_notice_xml(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> str:
    # TODO: add versions to publications
    pub_workspace_r = await get_publication_workspace_data(
        client=client, publication_workspace_id=publication_workspace_id
    )
    return pub_workspace_r["versions"][0]["notice"]["xmlContent"]


def is_new_notice_version_available(
    incoming_notice_ids: List[str], publication_workspace_id: str
) -> bool:
    with get_session() as session:
        return len(
            crud_publication.get_publication_by_workspace_id(
                publication_workspace_id=publication_workspace_id, session=session
            ).notice_ids
        ) < len(incoming_notice_ids)


def generate_uuid():
    return str(uuid.uuid4())


def get_nearest_business_day(date_obj: date = None) -> date:
    if date_obj is None:
        date_obj = date.today()  # get current date, without time

    if date_obj.weekday() == 5:  # Saturday
        return date_obj - timedelta(days=1)
    elif date_obj.weekday() == 6:  # Sunday
        return date_obj - timedelta(days=2)
    return date_obj


async def get_daily_pubproc_search_data(
    client: httpx.AsyncClient,
    interested_cpv_codes: List[CPVCodeSchema] = None,
) -> dict:
    token = get_token()

    latest_business_day = get_nearest_business_day()
    page_size = 100

    data = {
        "dispatch-date-from": f"{latest_business_day.strftime('%Y-%m-%d')}",
        "page": 1,
        "pageSize": page_size,
    }

    if interested_cpv_codes:
        cpv_codes = [cpv_code.code for cpv_code in interested_cpv_codes]
        data["cpv-codes"] = ", ".join(cpv_codes)

    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = await client.get(
        settings.pubproc_server + settings.path_sea_api + "/search/publications",
        params=data,
        headers=headers,
    )

    r_json = r.json()
    publications = r_json["publications"]
    total_count = int(r_json["totalCount"])

    if r.status_code == 200:
        pages = int(np.ceil(total_count / page_size))

        if pages > 1:
            for i in range(2, pages + 1):
                data["page"] = i
                r = await client.get(
                    settings.pubproc_server
                    + settings.path_sea_api
                    + "/search/publications",
                    params=data,
                    headers=headers,
                )
                publications.extend(r.json()["publications"])

    return publications


async def get_publication_workspace_data(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}",
        headers=headers,
    )

    return r.json()


@redis_cache("pubproc:documents")
async def get_publication_workspace_documents(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}/archive",
        headers=headers,
    )

    if r.status_code != 200:
        return {}

    zf = zipfile.ZipFile(BytesIO(r.content))
    file_map = {}

    for file_name in zf.namelist():
        file_data = BytesIO(zf.read(file_name))
        file_data.name = file_name
        file_map[file_name] = file_data

    return file_map


@redis_cache("pubproc:forum")
async def get_publication_workspace_forum(
    client: httpx.AsyncClient, forum_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/forums/{forum_id}/questions",
        headers=headers,
    )

    return r.json()
