from typing import List

from fastapi import APIRouter
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import BaseModel, EmailStr
from starlette.responses import JSONResponse

from app.config.settings import Settings
from app.schemas.publication_schemas import CompanySchema

settings = Settings()


email_router = APIRouter()


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


@email_router.post("/email")
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
