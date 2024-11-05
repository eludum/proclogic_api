from fastapi import FastAPI, Depends, BackgroundTasks, UploadFile, File, Form
from starlette.responses import JSONResponse
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr, BaseModel
import redis.asyncio as redis
from config.redis import create_redis
from typing import List
from contextlib import asynccontextmanager
import asyncio
import httpx


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cyclic_func())
    yield
    task.cancel()


async def cyclic_func():
    # TODO: add redis sync after mock connection, split into
    #       different sectors
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get('http://localhost:9005/mock')
                r.json()
            await asyncio.sleep(600)  # 60 seconds
        except Exception as e:
            print(f"Error in cyclic_func: {e}")
            await asyncio.sleep(60)  # wait a minute before retrying


async def get_redis() -> redis.Redis:
    return redis.Redis.from_pool(pool)


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/email/send")
async def send_in_background(
    background_tasks: BackgroundTasks,
    email: EmailSchema
) -> JSONResponse:

    message = MessageSchema(
        subject="Fastapi mail module",
        recipients=email.get("email"),
        body="Simple background task",
        subtype=MessageType.plain)

    fm = FastMail(conf)

    background_tasks.add_task(fm.send_message, message)

    return JSONResponse(status_code=200, content={"message": "email has been sent"})


@app.post("/email/send-file")
async def send_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    email: EmailStr = Form(...)
) -> JSONResponse:

    message = MessageSchema(
        subject="Fastapi mail module",
        recipients=[email],
        body="Simple background task",
        subtype=MessageType.html,
        attachments=[file])

    fm = FastMail(conf)

    background_tasks.add_task(fm.send_message, message)

    return JSONResponse(status_code=200, content={"message": "email has been sent"})


@app.get("/bid/{bid_id}")
def read_item(bid_id: int, cache=Depends(get_redis)):
    status = cache.get(bid_id)
    return {"item_name": status}


@app.put("/bid/{bid_id}")
def update_item(bid_id: int, cache=Depends(get_redis)):
    cache.set(bid_id, "available")
    return {"status": "available", "item_id": bid_id}


@app.get("/mock")
async def mock_db_data():
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
