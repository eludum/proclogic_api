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
from app.util.messages_helper import send_recommendation_notification
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.pubproc_token import get_token
from app.util.redis_cache import invalidate_publication_cache, redis_cache
from app.util.zip import unzip

settings = Settings()

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
        settings.pubproc_server + settings.path_sea_api + "/search/publications/byShortLink/mchv4u",
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
