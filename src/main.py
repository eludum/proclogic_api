import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import date
from typing import List

import httpx
from fastapi import FastAPI, status
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import BaseModel, EmailStr, TypeAdapter
from starlette.responses import JSONResponse

from ai.recommend import get_recommendation
from config.settings import Settings
from crud.company import get_all_companies
from crud.publication import (create_or_update_publication,
                              get_publication_by_workspace_id)
from schemas.publication_schemas import (CompanySchema, CPVCodeSchema,
                                         DescriptionSchema, PublicationSchema)
from util.alembic_runner import run_migration
from util.pubproc_token import get_token

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
    test_company = CompanySchema(
        vat_number="BE0893620715",
        name="EBM",
        email="info@ebmgroup.be",
        interested_cpv_codes=[
            CPVCodeSchema(
                code="45000000-7",
                descriptions=[
                    DescriptionSchema(
                        language="EN",
                        text="Construction work",
                    )
                ],
            )
        ],
        summary_activities="bouwwerkzaamheden",
        accreditations={},
        max_publication_value=1000000,
    )

    for pub in pubproc_data:
        logging.info(pub)
        # recom = get_recommendation(publication=pub, company=test_company)
        for company in get_all_companies():
            pass
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


@proclogic.get("/publication/{publication_workspace_id}")
async def get_publication(publication_workspace_id: str):
    return get_publication_by_workspace_id(publication_workspace_id)


async def get_pubproc_search_data() -> dict:
    token = get_token()
    today = date.today()

    data = {
        # TODO: add cpv based on sector in query
        # TODO: implement batch adding to sql server
        "currency-id": "82",
        "dispatch-date": f"{today.strftime('%d-%m-%Y')}",
        "page": 1,
        "pageSize": 100,
    }

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

async def get_pubproc_notice_data(notice_id= str) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }
    data = {
        # TODO: fix mediatype to html or pdf, not xml
        "Published": "True",
    }

    r = httpx.get(
        settings.pubproc_server + settings.path_dos_api + f"/notices/{notice_id}",
        params=data,
        headers=headers,
    )

    return r
