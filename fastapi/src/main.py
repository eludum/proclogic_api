import asyncio
from contextlib import asynccontextmanager
from typing import List
from datetime import datetime, date

import httpx
import redis.asyncio as redis
from fastapi import Depends, FastAPI
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import BaseModel, EmailStr
from starlette.responses import JSONResponse

from ai.openai import get_openai_answer
from config.postgres import get_sql
from config.redis import create_redis
from schemas.company import Company
from schemas.proclogic_notice_schemas import ProcLogicNotice
from schemas.pubproc_schemas import PubProc
from schemas.ted_schemas import Ted
from schemas.sector_schemas import Sector

from util.pubproc_token import get_token

from config.config import get_settings

settings = get_settings()

class EmailSchema(BaseModel):
    email: List[EmailStr]


pool = create_redis()

conf = ConnectionConfig(
    MAIL_USERNAME="username",
    MAIL_PASSWORD="**********",
    MAIL_FROM="test@email.com",
    MAIL_PORT=587,
    MAIL_SERVER="mail server",
    MAIL_FROM_NAME="Desired Name",
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
                await update_ted_publications()
            await asyncio.sleep(600)  # 10 minutes in seconds
        except Exception as e:
            print(f"Error in fetching of data: {e}")
            print("Retrying in 60 seconds...")
            await asyncio.sleep(60)  # wait a minute before retrying


async def update_ted_publications() -> None:
    redis_cache = await get_redis()
    sql_cache = await get_sql()

    pubproc_r = await get_pubproc_data()
    ted_r = await get_ted_data()
    pubproc_data = PubProc(**pubproc_r.json())
    ted_data = Ted(**ted_r.json())

    for publication in pubproc_data.publications:
        await redis_cache.json().set(str(publication.publicationReferenceNumbersBDA), "$", publication.model_dump_json())
        # TODO: crawl and add docs to redis ragged

    for notice in ted_data.notices:
        await redis_cache.json().set(str(notice.publication_number), "$", notice.model_dump_json())
        # TODO: crawl and add docs to redis ragged

    for notice in data.notices:
        for comp in sql_cache.query(Company).all():
            recomm = await get_openai_answer(notice, comp) #TODO: redis stream for summary?
            pn = ProcLogicNotice(notice=notice, company=comp, recommended=recomm)
            sql_cache.add(pn)


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

    fm = FastMail(conf)
    await fm.send_message(message, template_name="email_template.html")
    return JSONResponse(status_code=200, content={"message": "email has been sent"})


@app.get("company/{company_id}")
async def read_company(company_id: int, cache=Depends(get_sql)):
    cache.add()

@app.get("/publication/{pub_id}")
async def read_publication(pub_id: int, cache=Depends(get_redis)):
    status = cache.json().get(pub_id, "$")
    return {"item_name": status}

# TODO: shouldn't these be getting more data?
#       pagination?

async def get_ted_data(sector: Sector) -> dict:
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
        "limit": 10,
        "scope": "ACTIVE",
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER"
    }
    r = httpx.post('https://api.ted.europa.eu/v3/notices/search', json=data)
    return r


async def get_pubproc_data(sector: Sector) -> dict:
    token = get_token()
    today = date.today()

    data = {
        "currency-id": "82",
        "dispatch-date": f"{today.strftime("%d-%m-%Y")}",
    }
    headers = {
        'Authorization': f'Bearer {token["access_token"]}',
        'BelGov-Trace-Id': '2ce83af9-d524-43a6-8d1c-b19dff051aed'
    }
    r = httpx.get('https://public.pr.fedservices.be/api/eProcurementSea/v1/search/publications', params=data, headers=headers)    
    
    return r
