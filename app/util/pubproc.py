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

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.ai.recommend import (
    get_recommendation,
    summarize_xml,
    summarize_xml_get_award_info,
)
from app.config.settings import Settings
from app.schemas.publication_schemas import CPVCodeSchema, PublicationSchema
from app.util.pubproc_token import get_token

settings = Settings()


async def fetch_pubproc_data() -> None:
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await update_publications(client=client)
            await asyncio.sleep(600)  # 10 minutes in seconds
        except Exception as e:
            logging.error(e, "error in fetching data")
            await asyncio.sleep(60)  # wait a minute before retrying
        # TODO: remove continue in prod
        continue

        if pycron.is_now("0 6-19 * * 1-5"):
            try:
                async with httpx.AsyncClient() as client:
                    await update_publications(client=client)
            except Exception as e:
                logging.error(e, "error in fetching data")
        await asyncio.sleep(60)


async def update_publications(client: httpx.AsyncClient) -> None:
    pubproc_r = await get_daily_pubproc_search_data(client=client)

    pubproc_data = TypeAdapter(List[PublicationSchema]).validate_python(pubproc_r)
    print(pubproc_data)
    for pub in pubproc_data:

        existing_publication = crud_publication.publication_exists(
            publication_workspace_id=pub.publicationWorkspaceId
        )
        # TODO: add document summary and add forum questions, also add sector logic for company scan here
        if existing_publication and pub.vaultSubmissionDeadline is not None:
            if is_new_notice_version_available(
                incoming_notice_ids=pub.noticeIds,
                publication_workspace_id=pub.publicationWorkspaceId,
            ):
                xml_content = await get_notice_xml(
                    client=client, publication_workspace_id=pub.publicationWorkspaceId
                )
                ai_notice_summary = summarize_xml(xml_content)
                pub.ai_notice_summary = ai_notice_summary

        if not existing_publication and pub.vaultSubmissionDeadline is not None:
            xml_content = await get_notice_xml(
                client=client, publication_workspace_id=pub.publicationWorkspaceId
            )
            ai_notice_summary = summarize_xml(xml_content)
            pub.ai_notice_summary = ai_notice_summary
            for company in crud_company.get_all_companies():
                recom = get_recommendation(
                    publication=pub, company=company, notice_xml=xml_content
                )
                if recom:
                    if pub.recommended:
                        pub.recommended.append(company)
                    else:
                        pub.recommended = [company]

        # if pub.vaultSubmissionDeadline is None:
        # TODO: add field in model and schema to make sure we use these for report generation
        # info_json = summarize_xml_get_award_info(xml_content)

        crud_publication.get_or_create_publication(publication_schema=pub)


async def get_notice_xml(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> str:
    pub_workspace_r = await get_publication_workspace_data(
        client=client, publication_workspace_id=publication_workspace_id
    )
    return pub_workspace_r["versions"][0]["notice"]["xmlContent"]


def is_new_notice_version_available(
    incoming_notice_ids: List[str], publication_workspace_id: str
) -> True:
    return len(
        crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id
        ).notice_ids
    ) < len(incoming_notice_ids)


# TODO
# get all gunning publications, filter on who won the contract, make report
# get my publications, track publications for me, get notifications
# get recommended publications, make chart
# get sectors for onboarding part, get sector for each publication filter on sector


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
    client: httpx.AsyncClient, publication_workspace_id=str
) -> dict:

    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        # TODO: generate_uuid
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}",
        headers=headers,
    )

    return r.json()


async def get_publication_workspace_documents(
    client: httpx.AsyncClient, publication_workspace_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        # TODO: generate_uuid
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}/archive",
        headers=headers,
    )

    zf = zipfile.ZipFile(BytesIO(r.content))
    file_map = {}

    for file_name in zf.namelist():
        file_data = BytesIO(zf.read(file_name))
        file_data.name = file_name
        file_map[file_name] = file_data

    return file_map


async def get_publication_workspace_forum(
    client: httpx.AsyncClient, forum_id: str
) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        # TODO: generate_uuid
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = await client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/forums/{forum_id}/questions",
        headers=headers,
    )

    return r.json()


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
