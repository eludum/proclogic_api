from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class EmailTrackingCreate(BaseModel):
    contract_id: str
    recipient_email: EmailStr
    recipient_name: str
    email_subject: str
    email_content: str
    email_type: str = "contract_winner_notification"


class EmailTrackingResponse(BaseModel):
    id: int
    contract_id: str
    recipient_email: str
    recipient_name: str
    email_subject: str
    email_type: str
    sent_at: datetime
    is_delivered: bool
    delivery_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
