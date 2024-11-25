from fastapi import FastAPI, Depends, BackgroundTasks, UploadFile, File, Form
from starlette.responses import JSONResponse
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr, BaseModel
import redis.asyncio as redis
from config.redis import create_redis
from typing import List
from contextlib import asynccontextmanager
from schemas.pubproc_schemas import PubProc
from schemas.ted_schemas import Ted
from datetime import date
import asyncio
import httpx

from ai.openai import get_openai_answer


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
    task = asyncio.create_task(fetch_data(sector="bouw"))
    yield
    task.cancel()


async def fetch_data(sector) -> None:
    # TODO: add redis sync after mock connection, split into
    #       different sectors
    while True:
        try:
            async with httpx.AsyncClient() as client:
                pubproc_r = await client.get('http://localhost:9005/mock/pubproc')
                ted_r = await get_ted_data()
                # await update_pubproc_publications(pubproc_r.json(), sector)
                await update_ted_publications(ted_r.json(), sector)
            await asyncio.sleep(600)  # 10 minutes in seconds
        except Exception as e:
            print(f"Error in fetching of data: {e}")
            print("Retrying in 60 seconds...")
            await asyncio.sleep(60)  # wait a minute before retrying


async def update_pubproc_publications(data, sector) -> None:
    cache = await get_redis()
    model = PubProc(**data)
    # TODO: make internal model with psql where we store final output per publication
    #       fix sector logic
    for publication in model.publications:
        await cache.json().set(str(publication.id) + "_" + sector, "$", publication.model_dump_json())

    for publication in model.publications:
        # TODO: store final answer with internal model to psql use same IDs
        await get_openai_answer(publication)


async def update_ted_publications(data, sector) -> None:
    cache = await get_redis()
    model = Ted(**data)
    # TODO: make internal model with psql where we store final output per publication
    #       fix sector logic
    for publication in model.publications:
        await cache.json().set(str(publication.id) + "_" + sector, "$", publication.model_dump_json())

    for publication in model.publications:
        # TODO: store final answer with internal model to psql use same IDs
        await get_openai_answer(publication)


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello Procurement World!"}

# TODO: refactor, does this need to be an endpoint?
#       https://www.geeksforgeeks.org/email-templates-with-jinja-in-python/


@app.post("/email")
async def send_with_template(email: EmailSchema) -> JSONResponse:

    message = MessageSchema(
        subject="ProcLogic daily summary",
        recipients=email.get("email"),
        template_body=email.get("body"),
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message, template_name="email_template.html")
    return JSONResponse(status_code=200, content={"message": "email has been sent"})


@app.get("/publication/{pub_id}")
async def read_publication(pub_id: int, cache=Depends(get_redis)):
    status = cache.json().get(pub_id, "$")
    return {"item_name": status}

# TODO: implement redis pub sub for updates


async def get_ted_data() -> dict:
    # TODO: add pagination
    # TODO: add sorting
    # TODO: add filtering
    today = date.today()
    data = {
        # TODO: add cpv based on sector in query
        "query": f"publication-date={today.strftime("%Y%m%d")}",
        "fields": [
            "publication-date",
            "notice-title",
            "procedure-type",
            "contract-nature",
            # TODO fix country
            # "country",
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


@app.get("/mock/pubproc")
async def mock_pubproc_data() -> dict:
    # TODO: make better mock data
    # TODO: add pagination
    # TODO: add sorting
    # TODO: add filtering
    # TODO: add TED db (European Single Procurement Document)
    return {
        "totalCount": 0,
        "publications": [
            {
                "id": 0,
                "referenceNumber": "string",
                "insertionDate": "2022-03-10",
                "organisation": {
                    "organisationId": 0,
                    "tree": "string",
                    "organisationNames": [
                        {
                            "text": "string",
                            "language": "NL"
                        }
                    ]
                },
                "cancelledAt": "2022-03-10T12:15:50",
                "dossier": {
                    "titles": [
                        {
                            "text": "string",
                            "language": "NL"
                        }
                    ],
                    "descriptions": [
                        {
                            "text": "string",
                            "language": "NL"
                        }
                    ],
                    "accreditations": {
                        "additionalProp1": 0,
                        "additionalProp2": 0,
                        "additionalProp3": 0
                    },
                    "referenceNumber": "string",
                    "procurementProcedureType": "OPEN",
                    "specialPurchasingTechnique": "FRAMEWORK_AGREEMENT",
                    "legalBasis": "D23"
                },
                "lots": [
                    {
                        "titles": [
                            {
                                "text": "string",
                                "language": "NL"
                            }
                        ],
                        "descriptions": [
                            {
                                "text": "string",
                                "language": "NL"
                            }
                        ],
                        "reservedParticipation": [
                            "NONE"
                        ],
                        "reservedExecution": [
                            "YES"
                        ]
                    }
                ],
                "publicationWorkspaceId": "string",
                "cpvMainCode": {
                    "code": "string",
                    "descriptions": [
                        {
                            "text": "string",
                            "language": "NL"
                        }
                    ]
                },
                "cpvAdditionalCodes": [
                    {
                        "code": "string",
                        "descriptions": [
                            {
                                "text": "string",
                                "language": "NL"
                            }
                        ]
                    }
                ],
                "natures": [
                    "WORKS"
                ],
                "publicationLanguages": [
                    "NL"
                ],
                "nutsCodes": [
                    "string"
                ],
                "dispatchDate": "2022-03-10",
                "sentAt": [
                    "2022-03-10T12:15:50"
                ],
                "publishedAt": [
                    "2022-03-10T12:15:50"
                ],
                "vaultSubmissionDeadline": "2022-03-10T12:15:50",
                "tedPublished": "true",
                "noticeSubType": "string",
                "noticeIds": [
                    "string"
                ],
                "procedureId": "string"
            }
        ]
    }
