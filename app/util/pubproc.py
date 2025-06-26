import asyncio
import logging
import uuid
from datetime import date
from typing import List

import httpx
import numpy as np
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.ai.recommend import (
    get_recommendation,
    summarize_publication_contract,
    summarize_publication_with_files,
    summarize_publication_without_files,
)
from app.config.postgres import get_session
from app.config.settings import Settings
from app.schemas.company_schemas import CompanyPublicationMatchSchema
from app.schemas.publication_schemas import CPVCodeSchema, PublicationSchema
from app.services.contract_email import handle_new_contract_created
from app.util.messages_helper import send_deadline_notification, send_recommendation_notification
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.pubproc_token import get_token
from app.util.redis_cache import invalidate_publication_cache, redis_cache
from app.util.zip import unzip
from proclogic_api.app.crud.notification import cleanup_old_notifications, has_recent_deadline_notification

settings = Settings()


async def fetch_pubproc_data() -> None:
    logging.info("Starting publication data fetch service")
    while True:
        try:
            # TODO: scan all saved publications and check if they have changed documents or forum
            # TODO: USE AP SCHEDULER NOT PYCRON
            try:
                async with httpx.AsyncClient() as client:
                    await retrieve_publications(client=client)
                    logging.info("Publication data fetch completed successfully")
            except Exception as e:
                logging.error("Error in fetching data: %s", e)

            # Wait until next run
            await asyncio.sleep(3600)  # 1 hour in seconds

        except asyncio.CancelledError:
            logging.info("Publication data fetch service is shutting down")
            raise  # Re-raise to allow proper cleanup


async def update_pubproc_data() -> None:
    logging.info("Starting publication data update service")
    try:
        while True:
            try:
                # check_document_changes()
                # check_forum_changes()
                # TODO: save documents in db and send notification if saved and docs change
                pass
            except Exception as e:
                logging.error("Error in updating pubproc data: %s", e)
            await asyncio.sleep(3600)  # 1 hour in seconds
    except asyncio.CancelledError:
        logging.info("Publication data update service is shutting down")
        raise


async def gather_notifications() -> None:
    """
    Enhanced notification service that sends deadline notifications
    and other periodic notifications.
    """
    logging.info("Starting notification gathering service")
    try:
        while True:
            try:
                await send_deadline_notifications()
                await perform_notification_maintenance()
                logging.info("Notification gathering completed successfully")
            except Exception as e:
                logging.error("Error in gathering notifications: %s", e)
            
            # Wait 6 hours before next notification check
            await asyncio.sleep(21600)  # 6 hours in seconds
            
    except asyncio.CancelledError:
        logging.info("Notification gathering service is shutting down")
        raise

async def send_deadline_notifications() -> None:
    """
    Send deadline reminder notifications for approaching deadlines.
    """
    logging.info("Sending deadline notifications")
    
    try:
        with get_session() as session:
            # Get publications with deadlines in the next 7, 3, and 1 days
            for days_ahead in [7, 3, 1]:
                deadline_publications = crud_publication.get_publications_with_upcoming_deadlines(
                    session, days_ahead
                )
                
                for publication, company_vat_number, days_left in deadline_publications:
                    try:
                        # Check if we already sent a notification for this deadline period
                        if not has_recent_deadline_notification(
                            company_vat_number, publication.publication_workspace_id, days_ahead, session
                        ):
                            await send_deadline_notification(
                                company_vat_number=company_vat_number,
                                publication_id=publication.publication_workspace_id,
                                publication_title=PublicationConverter.get_descr_as_str(
                                    publication.dossier.titles
                                ),
                                days_left=days_left
                            )
                            
                    except Exception as e:
                        logging.error(
                            f"Error sending deadline notification: {e}"
                        )
            
    except Exception as e:
        logging.error(f"Error sending deadline notifications: {e}")


async def perform_notification_maintenance() -> None:
    """
    Perform maintenance tasks like cleaning up old notifications.
    """
    try:
        with get_session() as session:
            # Clean up old read notifications (older than 180 days)
            cleanup_count = cleanup_old_notifications(session, days_to_keep=180)
            if cleanup_count > 0:
                logging.info(f"Cleaned up {cleanup_count} old notifications")
                
    except Exception as e:
        logging.error(f"Error in notification maintenance: {e}")


async def retrieve_publications(client: httpx.AsyncClient) -> None:
    """
    Main function that retrieves and processes publications.
    """
    with get_session() as session:
        pubproc_r = await get_daily_pubproc_search_data(client=client)
        pubproc_data = TypeAdapter(List[PublicationSchema]).validate_python(pubproc_r)

        # Process each publication
        for pub in pubproc_data:
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

    # Check if the publication already exists
    existing_publication = crud_publication.publication_exists(
        publication_workspace_id=pub.publication_workspace_id, session=session
    )

    if existing_publication and pub.vault_submission_deadline is not None:

        await update_existing_publication(client=client, pub=pub, session=session)
    elif not existing_publication and pub.vault_submission_deadline is not None:

        await create_new_publication(client=client, pub=pub, session=session)
    elif not existing_publication and pub.vault_submission_deadline is None:
        # TODO: get the actual publication
        # e.g.  https://www.publicprocurement.be/publication-workspaces/cde195bc-c647-4792-8859-19a853a0339b/general
        await process_publication_contract(client=client, pub=pub, session=session)


async def update_existing_publication(
    client: httpx.AsyncClient, pub: PublicationSchema, session: Session
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

        # Get documents
        filesmap = await get_publication_workspace_documents(
            client=client, publication_workspace_id=pub.publication_workspace_id
        )

        # TODO: put update in timeline on the frontend

        # TODO: add forum data to ai
        # Get forum info, get forum_id
        # forum = await get_publication_workspace_forum(
        #     client=client, publication_workspace_id=pub.publication_workspace_id
        # )

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
    client: httpx.AsyncClient, pub: PublicationSchema, session: Session
) -> None:
    """
    Create a new publication and generate recommendations for companies.
    """
    xml_content = await get_notice_xml(
        client=client, publication_workspace_id=pub.publication_workspace_id
    )

    # Get documents
    filesmap = await get_publication_workspace_documents(
        client=client, publication_workspace_id=pub.publication_workspace_id
    )

    # TODO: add forum data to ai
    # Get forum info
    # forum = await get_publication_workspace_forum(
    #     client=client, publication_workspace_id=pub.publication_workspace_id
    # )

    # Add AI-generated content
    await enrich_publication_with_ai(
        pub=pub, xml_content=xml_content, filesmap=filesmap
    )

    # First create the publication
    crud_publication.get_or_create_publication(publication_schema=pub, session=session)

    # Then generate recommendations
    await generate_company_recommendations(pub=pub, session=session)


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

    contract = summarize_publication_contract(xml=xml_content)
    if contract:
        pub.contract = contract
        crud_publication.get_or_create_publication(
            publication_schema=pub, session=session
        )
        await handle_new_contract_created(
            publication=pub,
            session=session,
        )
    else:
        logging.info(
            "No contract found for publication %s", pub.publication_workspace_id
        )


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
            pub.estimated_value = int(estimated_value)
        except Exception as e:
            logging.error(f"Error in summarize_publication_with_files: {e}")
    else:
        try:
            pub.ai_summary_without_documents = summarize_publication_without_files(
                publication=pub, xml=xml_content
            )
        except Exception as e:
            logging.error(f"Error in summarize_publication_without_files: {e}")


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

                # Send notification about the recommendation
                # TODO: asyncio.create_task(
                await send_recommendation_notification(
                    company_vat_number=company.vat_number,
                    publication_id=pub.publication_workspace_id,
                    publication_title=PublicationConverter.get_descr_as_str(
                        pub.dossier.titles
                    ),
                    publication_submission_deadline=pub.vault_submission_deadline,
                )
        except Exception as e:
            logging.error(
                f"Error generating recommendation for company {company.vat_number}: {e}"
            )

    # If we have matches, update the publication
    if match_schemas:
        # Add matches to publication schema before saving
        pub.company_matches = match_schemas

        crud_publication.get_or_create_publication(
            publication_schema=pub, session=session
        )


async def get_notice_xml(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> str:
    # TODO: add versions to publications, also key "versions" errors sometimes
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


async def get_daily_pubproc_search_data(
    client: httpx.AsyncClient,
    interested_cpv_codes: List[CPVCodeSchema] = None,
) -> dict:
    token = get_token()

    today = date.today()
    page_size = 100

    # TODO: go page by page and stop if we hit already processed ones, to limit api usage
    data = {
        "dispatchDateFrom": f"{today.strftime('%Y-%m-%d')}",
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


async def get_publication_workspace_document_list(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> List[str]:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}/documents",
        headers=headers,
    )

    data = r.json()

    documents = []
    for file in data:
        filename = file["versions"][0]["document"]["originalFileName"]
        documents.append(filename)

    return documents


async def get_publication_workspace_document_external_urls(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> List[str]:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}/urls",
        headers=headers,
    )

    data = r.json()

    urls = []
    for url in data:
        urls.append(url["url"])

    return urls


@redis_cache("pubproc:documents")
async def get_publication_workspace_documents(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    # TODO: send notification if saved and docs change
    # add external links

    try:
        # Add a 5-minute timeout for large files
        r = await client.get(
            settings.pubproc_server
            + settings.path_dos_api
            + f"/publication-workspaces/{publication_workspace_id}/archive",
            headers=headers,
            timeout=300,  # 5 minutes
        )

        if r.status_code != 200:
            return {}

        # Process the zip file
        return unzip(
            zip_bytes=r.content, publication_workspace_id=publication_workspace_id
        )

    except asyncio.TimeoutError:
        logging.error(
            f"Timeout while downloading archive for {publication_workspace_id}"
        )
        return {}
    except Exception as e:
        logging.error(
            f"Error downloading documents for {publication_workspace_id}: {str(e)}"
        )
        return {}


async def get_publication_workspace_forum(
    client: httpx.AsyncClient, forum_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": generate_uuid(),
    }

    # TODO: display in frontend, TODO: send forum if saved and docs change

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/forums/{forum_id}/questions",
        headers=headers,
    )

    if r.status_code != 200:
        return {}

    return r.json()
