import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import List

import httpx
import xmltodict
from app.ai.recommend import get_recommendation
from app.config.settings import Settings
from app.crud.company import get_all_companies
from app.crud.publication import create_or_update_publication
from fastapi import FastAPI, status
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import BaseModel, EmailStr, TypeAdapter
from app.schemas.publication_schemas import (
    CompanySchema,
    CPVCodeSchema,
    DescriptionSchema,
    PublicationSchema,
)
from starlette.responses import JSONResponse
from app.util.alembic_runner import run_migration
from app.util.pubproc_token import get_token

settings = Settings()

logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG if settings.debug_logs else logging.INFO
)


class EmailSchema(BaseModel):
    email: List[EmailStr]


email_conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=465,
    MAIL_SERVER="smtp-auth.mailprotect.be",
    MAIL_FROM_NAME="ProcLogic",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(fetch_data())
    # run_migration()
    yield
    task.cancel()


async def fetch_data() -> None:
    while True:
        try:
            async with httpx.AsyncClient():
                await update_publications()
            await asyncio.sleep(600)  # 10 minutes in seconds
        except Exception as e:
            logging.error(e, "error in fetching data")
            logging.info("retrying in 60 seconds")
            await asyncio.sleep(60)  # wait a minute before retrying


async def update_publications() -> None:
    pubproc_r = await get_pubproc_search_data()

    pubproc_data = TypeAdapter(List[PublicationSchema]).validate_python(pubproc_r)

    for pub in pubproc_data:
        for company in get_all_companies():
            recom = get_recommendation(publication=pub, company=company)
            if recom:
                pub.recommended.append(company)
        create_or_update_publication(publication_data=pub)
        break


proclogic = FastAPI(lifespan=lifespan)


class HealthCheck(BaseModel):
    """Response model to validate and return when performing a health check."""

    status: str = "OK"


@proclogic.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """
    ## Perform a Health Check
    Endpoint to perform a healthcheck on. This endpoint can primarily be used Docker
    to ensure a robust container orchestration and management is in place. Other
    services which rely on proper functioning of the API service will not deploy if this
    endpoint returns any other HTTP status code except 200 (OK).
    Returns:
        HealthCheck: Returns a JSON response with the health status
    """
    return HealthCheck(status="OK")


# TODO: refactor, does this need to be an endpoint?
#       https://www.geeksforgeeks.org/email-templates-with-jinja-in-python/


@proclogic.post("/email")
async def send_with_template(
    email: EmailSchema, company: CompanySchema
) -> JSONResponse:

    message = MessageSchema(
        subject="ProcLogic daily summary",
        recipients=email.get("email"),
        template_body=email.get("body"),
        subtype=MessageType.html,
    )

    fm = FastMail(email_conf)
    # TODO: fix email template make it pretty
    await fm.send_message(message, template_name="email_template.html")
    return JSONResponse(status_code=200, content={"message": "email has been sent"})


async def get_pubproc_search_data(
    interested_cpv_codes: List[CPVCodeSchema] = None,
) -> dict:
    token = get_token()
    today = date.today()

    data = {
        # TODO: add cpv based on sector in query
        # TODO: implement batch adding to sql server
        "dispatch-date": f"{today.strftime('%d-%m-%Y')}",
        "page": 1,
        "pageSize": 100,
    }

    if interested_cpv_codes:
        cpv_codes = [cpv_code.code for cpv_code in interested_cpv_codes]
        data["cpv-codes"] = ", ".join(cpv_codes)

    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = httpx.get(
        settings.pubproc_server + settings.path_sea_api + "/search/publications",
        params=data,
        headers=headers,
    )

    publications = r.json()["publications"]

    if r.status_code == 200:
        totalCount = r.json()["totalCount"]
        pages = int(totalCount / 100)

        for i in range(2, pages + 1):
            data["page"] = i
            r = httpx.get(
                settings.pubproc_server
                + settings.path_sea_api
                + "/search/publications",
                params=data,
                headers=headers,
            )
            publications.extend(r.json()["publications"])
            # TODO: delete break
            break

    return publications


async def get_publication_workspace_data(publication_workspace_id=str) -> dict:

    # TODO: get amount of award, documents, forum, external links, all versions of publication

    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        # TODO: generate_uuid
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = httpx.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}",
        headers=headers,
    )

    return r.json()


def generate_uuid():
    return str(uuid.uuid4())
