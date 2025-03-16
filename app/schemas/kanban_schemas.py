from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

# Base schemas for creating and updating
class KanbanStatusBase(BaseModel):
    name: str
    color: str
    position: int = 0
    is_default: bool = False


class KanbanStatusCreate(KanbanStatusBase):
    pass


class KanbanStatusUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    is_default: Optional[bool] = None


# Response schemas
class KanbanStatusResponse(KanbanStatusBase):
    id: int
    company_vat_number: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Base schemas for Publication Status
class PublicationStatusBase(BaseModel):
    status_id: int
    notes: Optional[str] = None
    position: int = 0


class PublicationStatusCreate(PublicationStatusBase):
    publication_workspace_id: str


class PublicationStatusUpdate(BaseModel):
    status_id: Optional[int] = None
    notes: Optional[str] = None
    position: Optional[int] = None


# Response schema for Publication Status
class PublicationStatusResponse(PublicationStatusBase):
    company_vat_number: str
    publication_workspace_id: str
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Special response schemas for the Kanban board view
class PublicationInKanban(BaseModel):
    publication_workspace_id: str
    title: str
    organisation: str
    submission_deadline: Optional[datetime] = None
    is_active: bool
    notes: Optional[str] = None
    position: int
    match_percentage: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)


class KanbanColumn(BaseModel):
    id: int
    name: str
    color: str
    position: int
    is_default: bool
    publications: List[PublicationInKanban] = Field(default_factory=PublicationInKanban)
    
    model_config = ConfigDict(from_attributes=True)


class KanbanBoard(BaseModel):
    columns: List[KanbanColumn]
    
    model_config = ConfigDict(from_attributes=True)


# Schema for moving a publication between statuses
class MovePublicationRequest(BaseModel):
    publication_workspace_id: str
    new_status_id: int
    new_position: int
