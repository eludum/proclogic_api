from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    citations: Optional[str] = None


class MessageCreate(MessageBase):
    pass


class MessageSchema(MessageBase):
    id: int
    conversation_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationBase(BaseModel):
    publication_workspace_id: str
    company_vat_number: str


class ConversationCreate(ConversationBase):
    pass


class ConversationSchema(ConversationBase):
    id: int
    created_at: datetime
    updated_at: datetime
    assistant_id: Optional[str] = None
    thread_id: Optional[str] = None
    is_active: bool
    messages: List[MessageSchema] = Field(default_factory=MessageSchema)

    model_config = ConfigDict(from_attributes=True)


class ConversationSummary(BaseModel):
    id: int
    publication_workspace_id: str
    publication_title: str
    updated_at: datetime
    last_message_preview: Optional[str] = None
    message_count: int

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    publication_workspace_id: str
    message: str
    conversation_id: Optional[int] = None


class ChatResponse(BaseModel):
    conversation_id: int
    message: MessageSchema