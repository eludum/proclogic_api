from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class KanbanStatus(Base):
    """Model for custom Kanban statuses that a company can create."""
    __tablename__ = "kanban_statuses"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(50))  # For UI display
    position: Mapped[int] = mapped_column(Integer, default=0)  # For ordering
    company_vat_number: Mapped[str] = mapped_column(ForeignKey("companies.vat_number"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="kanban_statuses")
    publication_statuses = relationship("PublicationStatus", back_populates="status", cascade="all, delete-orphan")


class PublicationStatus(Base):
    """Model for tracking the status of a publication within a company's Kanban board."""
    __tablename__ = "publication_statuses"

    # Composite primary key
    company_vat_number: Mapped[str] = mapped_column(ForeignKey("companies.vat_number"), primary_key=True)
    publication_workspace_id: Mapped[str] = mapped_column(ForeignKey("publications.publication_workspace_id"), primary_key=True)
    
    # Status details
    status_id: Mapped[int] = mapped_column(ForeignKey("kanban_statuses.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)  # Position within the status column
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="publication_statuses")
    publication = relationship("Publication", back_populates="status_entries")
    status = relationship("KanbanStatus", back_populates="publication_statuses")