from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class EmailTrackingResponse(BaseModel):
    id: int
    contract_id: str
    recipient_email: str
    recipient_name: str
    email_type: str
    sent_at: datetime
    is_delivered: bool
    delivery_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
