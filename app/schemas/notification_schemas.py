from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationBase(BaseModel):
    title: str
    content: str
    notification_type: str = Field(
        ...,
        description="Type of notification: recommendation, deadline, system, forum, account",
    )
    link: Optional[str] = None
    related_entity_id: Optional[str] = None


class NotificationCreate(NotificationBase):
    company_vat_number: str


class NotificationResponse(NotificationBase):
    id: int
    is_read: bool
    created_at: datetime
    company_vat_number: str

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread: int
