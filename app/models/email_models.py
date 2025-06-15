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


class ContractEmailTracking(Base):
    """Track emails sent to contract winners"""

    __tablename__ = "contract_email_tracking"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"))
    recipient_email: Mapped[str] = mapped_column(String(255))
    recipient_name: Mapped[str] = mapped_column(String(255))
    email_subject: Mapped[str] = mapped_column(String(500))
    email_content: Mapped[str] = mapped_column(Text)
    email_type: Mapped[str] = mapped_column(
        String(50), default="contract_winner_notification"
    )

    # Tracking fields
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    is_delivered: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    contract = relationship("Contract", back_populates="email_tracking")
