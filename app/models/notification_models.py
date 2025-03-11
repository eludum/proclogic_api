from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(
        String(50)
    )  # recommendation, deadline, system, forum, account
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Foreign keys
    company_vat_number: Mapped[str] = mapped_column(ForeignKey("companies.vat_number"))
    related_entity_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # For linking to publications, forums, etc.

    # Relationships
    company = relationship("Company", back_populates="notifications")
