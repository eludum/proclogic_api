from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, PickleType, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    sector: Mapped[str] = mapped_column(String)
    cpv_codes: Mapped[List[str]] = mapped_column(ARRAY(String))
    company_vat_number: Mapped[str] = mapped_column(ForeignKey("companies.vat_number"))

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="interested_sectors")


class Company(Base):
    __tablename__ = "companies"

    # Primary identification
    vat_number: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    emails: Mapped[List[str]] = mapped_column(ARRAY(String), index=True)

    # Company profile data
    subscription: Mapped[str] = mapped_column(String)
    number_of_employees: Mapped[int] = mapped_column(Integer, default=1)
    summary_activities: Mapped[str] = mapped_column(String)
    accreditations: Mapped[Optional[dict]] = mapped_column(PickleType, nullable=True)
    max_publication_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Trial and subscription management
    trial_start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    trial_end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    is_trial_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    subscription_status: Mapped[str] = mapped_column(
        String(50), default="inactive", index=True
    )  # inactive, trial, active, cancelled, past_due

    # Keywords extracted from activities for better matching
    activity_keywords: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Geographic areas of operation (NUTS codes)
    operating_regions: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Relationships
    interested_sectors: Mapped[List["Sector"]] = relationship(back_populates="company")
    publication_matches: Mapped[List["CompanyPublicationMatch"]] = relationship(
        back_populates="company"
    )
    conversations: Mapped[List["Conversation"]] = relationship(back_populates="company")
    notifications: Mapped[List["Notification"]] = relationship(back_populates="company")
    kanban_statuses: Mapped[List["KanbanStatus"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    publication_statuses: Mapped[List["PublicationStatus"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    # Helper properties for common queries
    @property
    def recommended_publications(self):
        return [
            match.publication
            for match in self.publication_matches
            if match.is_recommended
        ]

    @property
    def saved_publications(self):
        return [
            match.publication for match in self.publication_matches if match.is_saved
        ]

    @property
    def has_valid_subscription(self) -> bool:
        """Check if company has a valid subscription (active paid or active trial)"""
        if self.subscription_status == "active":
            return True

        if self.is_trial_active and self.trial_end_date:
            return datetime.now() <= self.trial_end_date

        return False

    @property
    def is_trial_expired(self) -> bool:
        """Check if trial has expired"""
        if not self.trial_end_date:
            return False
        return datetime.now() > self.trial_end_date

    def start_trial(self, trial_days: int = 7) -> None:
        """Start a 7-day trial for the company"""
        now = datetime.now()
        self.trial_start_date = now
        self.trial_end_date = now + timedelta(days=trial_days)
        self.is_trial_active = True
        self.subscription_status = "trial"

    def end_trial(self) -> None:
        """End the trial period"""
        self.is_trial_active = False
        if self.subscription_status == "trial":
            self.subscription_status = "inactive"


from app.models.conversation_models import Conversation
from app.models.notification_models import Notification
