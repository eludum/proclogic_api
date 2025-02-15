import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import List

import httpx
import pycron
import logging
import numpy as np
from fastapi import Depends, FastAPI, status
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import BaseModel, EmailStr, TypeAdapter
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.ai.recommend import get_recommendation
from app.config.postgres import get_session_generator
from app.config.settings import Settings
from app.crud.mapper import convert_publication_to_out_schema, convert_company_to_schema
from app.models.publication_models import Publication
from app.schemas.publication_out_schemas import PublicationOut
from app.schemas.publication_schemas import (
    CompanySchema,
    CPVCodeSchema,
    PublicationSchema,
)
from app.util.alembic_runner import run_migration
from app.util.pubproc_token import get_token

settings = Settings()

logging.basicConfig(handlers=[logging.StreamHandler()])


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
    run_migration()
    task = asyncio.create_task(fetch_data())
    yield
    task.cancel()


async def fetch_data() -> None:
    while True:
        if settings.pubproc_server == "https://public.int.fedservices.be":
            try:
                async with httpx.AsyncClient() as client:
                    await update_publications(client=client)
                await asyncio.sleep(600)  # 10 minutes in seconds
            except Exception as e:
                logging.error(e, "error in fetching data")
                await asyncio.sleep(60)  # wait a minute before retrying
            continue

        if pycron.is_now("0 6-19 * * 1-5"):
            try:
                async with httpx.AsyncClient() as client:
                    await update_publications(client=client)
            except Exception as e:
                logging.error(e, "error in fetching data")
        await asyncio.sleep(60)


async def update_publications(client: httpx.AsyncClient) -> None:
    return ""
    pubproc_r = await get_daily_pubproc_search_data(client=client)

    pubproc_data = TypeAdapter(List[PublicationSchema]).validate_python(pubproc_r)
    for pub in pubproc_data:

        # TODO: fetch workspace data
        # pub_workspace_r = await get_publication_workspace_data(
        #     client=client, publication_workspace_id=pub.publication_workspace_id
        # )
        # pub_workspace_data = TypeAdapter(PublicationWorkspaceSchema).validate_python(
        #     pub_workspace_r
        # )
        for company in crud_company.get_all_companies():
            com_interested_cpv_codes = [cpv_code.code for cpv_code in company.interested_cpv_codes]
            publication_cpv_codes = [cpv_code.code for cpv_code in pub.cpvAdditionalCodes] + [pub.cpvMainCode.code]
            res = list(set(com_interested_cpv_codes) & set(publication_cpv_codes))
            if res:
            # TODO: add prefiltering based on CPV codes interested by company
                recom = get_recommendation(publication=pub, company=company)
                if recom == "yes":
                    pub.recommended.append(company)
            
        crud_publication.create_or_update_publication(publication_data=pub)


proclogic = FastAPI(lifespan=lifespan, debug=True)

origins = [
    "http://localhost",
    "http://localhost:3000",
]

proclogic.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return JSONResponse(content={"message": "email has been sent"})


@proclogic.post("/company/")
async def create_company(company: CompanySchema) -> CompanySchema:
    return crud_company.create_company(vat_number=company.vat_number, **company.dict())


@proclogic.patch("/company/{vat_number}")
async def update_company(vat_number: str, company: CompanySchema) -> CompanySchema:
    return crud_company.update_company(vat_number=vat_number, **company.dict())


@proclogic.delete("/company/{vat_number}")
async def delete_company(vat_number: str) -> JSONResponse:
    return crud_company.delete_company(vat_number=vat_number)


@proclogic.get("/company/{email}", response_model=CompanySchema)
async def get_company_by_email(
    email: str, session: Session = Depends(get_session_generator)
) -> CompanySchema:
    company = crud_company.get_company_by_email(email=email, session=session)
    company = convert_company_to_schema(company) if company else None
    return company if company else JSONResponse(status_code=404, content={"message": "Company not found"})


@proclogic.get("/publication/{company_vatnumber}/", response_model=List[PublicationOut])
async def get_publications_by_vat(
    company_vatnumber: str, session: Session = Depends(get_session_generator)
) -> List[PublicationOut]:
    publications = crud_publication.get_all_publications(  # or planning publications
        session=session
    )

    company = crud_company.get_company_by_vat_number(vat_number=company_vatnumber, session=session)

    # TODO: filter on VAULT SUBMISSION DEADLINE TO SEE IF ACTIVE ALSO SUBMISSION DEADLINE
    return [convert_publication_to_out_schema(publication=publication, company=company) for publication in publications]


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
                publications.extend((await r.json())["publications"])

    return publications


async def get_publication_workspace_data(
    client: httpx.AsyncClient, publication_workspace_id=str
) -> dict:

    # TODO: get amount of award, documents, forum, external links, all versions of publication
    #       fix return type
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        # TODO: generate_uuid
        "BelGov-Trace-Id": "2ce83af9-d524-43a6-8d1c-b19dff051aed",
    }

    r = client.get(
        settings.pubproc_server
        + settings.path_dos_api
        + f"/publication-workspaces/{publication_workspace_id}",
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
