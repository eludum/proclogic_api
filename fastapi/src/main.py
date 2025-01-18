import asyncio
from contextlib import asynccontextmanager
from typing import List
from datetime import datetime, date

import httpx
import redis.asyncio as redis
from fastapi import Depends, FastAPI
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import BaseModel, EmailStr, TypeAdapter
from starlette.responses import JSONResponse

from ai.openai import get_openai_answer
from config.postgres import get_sql
from config.redis import create_redis
from schemas.company import Company
from schemas.proclogic_notice_schemas import ProcLogicPublication
from schemas.pubproc_schemas import Publication
from schemas.ted_schemas import Notice
from schemas.sector_schemas import Sector

from util.pubproc_token import get_token

from config.settings import Settings

settings = Settings()

class EmailSchema(BaseModel):
    email: List[EmailStr]


pool = create_redis()

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
    VALIDATE_CERTS=True
)


async def get_redis() -> redis.Redis:
    return redis.Redis.from_pool(pool)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: cpv code filter here
    task = asyncio.create_task(fetch_data())
    yield
    task.cancel()


async def fetch_data() -> None:
    while True:
        try:
            async with httpx.AsyncClient():
                await update_publications()
            await asyncio.sleep(600)  # 10 minutes in seconds
        except Exception as e:
            print(f"Error in fetching of data: {e}")
            print("Retrying in 60 seconds...")
            await asyncio.sleep(60)  # wait a minute before retrying


async def update_publications() -> None:
    psql = get_sql()

    pubproc_r = await get_pubproc_data()
    # ted_r = await get_ted_data()

    pubproc_data = TypeAdapter(list[Publication]).validate_python(pubproc_r)
    # ted_data = TypeAdapter(list[Notice]).validate_python(ted_r)

    for pub in pubproc_data:
        for comp in psql.query(Company).all():
            recomm = await get_openai_answer(pub, comp) #TODO: redis stream for summary?
            pn = ProcLogicPublication(original_notice=pub, company=comp, recommended=recomm)
            psql.add(pn)

    # for notice in data.notices:
    #     for comp in sql_cache.query(Company).all():
    #         recomm = await get_openai_answer(notice, comp) #TODO: redis stream for summary?
    #         pn = ProcLogicNotice(notice=notice, company=comp, recommended=recomm)
    #         sql_cache.add(pn)


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World!"}

# TODO: refactor, does this need to be an endpoint?
#       https://www.geeksforgeeks.org/email-templates-with-jinja-in-python/

@app.post("/email")
async def send_with_template(email: EmailSchema, company: Company) -> JSONResponse:

    message = MessageSchema(
        subject="ProcLogic daily summary",
        recipients=email.get("email"),
        template_body=email.get("body"),
        subtype=MessageType.html,
    )

    fm = FastMail(email_conf)
    await fm.send_message(message, template_name="email_template.html")
    return JSONResponse(status_code=200, content={"message": "email has been sent"})

# TODO: shouldn't these be getting more data?
#       pagination?

async def get_ted_data() -> dict:
    today = date.today()
    data = {
        # TODO: add cpv based on sector in query
        "query": f'publication-date={today.strftime("%Y%m%d")} AND buyer-country=BEL',
        "fields": [
            "publication-date",
            "notice-title",
            "procedure-type",
            "contract-nature",
            "tender-value",
            "tender-value-cur",
            "classification-cpv",
            "organisation-contact-point-tenderer",
            "document-url-lot"
        ],
        "page": 1,
        "limit": 100,
        "scope": "ACTIVE",
        "checkQuerySyntax": False,
        "paginationMode": "ITERATION"
    }
    r = httpx.post('https://api.ted.europa.eu/v3/notices/search', json=data)

    notices = r.json()['notices']

    while "iterationNextToken" in r.json():
        data['iterationNextToken'] = r.json()['iterationNextToken']
        r = httpx.post('https://api.ted.europa.eu/v3/notices/search', json=data)
        notices.extend(r.json()['notices'])
        break

    return notices


async def get_pubproc_data() -> dict:
    token = get_token()
    today = date.today()

    data = {
        # TODO: add cpv based on sector in query
        "currency-id": "82",
        "dispatch-date": f"{today.strftime('%d-%m-%Y')}",
        "page": 1,
        "pageSize": 100
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'BelGov-Trace-Id': '2ce83af9-d524-43a6-8d1c-b19dff051aed'
    }

    print(headers)

    r = httpx.get('https://public.int.fedservices.be/api/eProcurementSea/v1/search/publications', params=data, headers=headers)    

    print(r)

    publications = r.json()['publications']

    if r.status_code == 200:
        totalCount = r.json()['totalCount']
        pages = int(totalCount / 100)

        for i in range(2, pages + 1):
            data['page'] = i
            print(data)
            r = httpx.get('https://public.int.fedservices.be/api/eProcurementSea/v1/search/publications', params=data, headers=headers)
            publications.extend(r.json()['publications'])
            break

    return publications
