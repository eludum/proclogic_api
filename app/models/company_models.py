from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    Float,
    ForeignKey,
    Integer,
    PickleType,
    String,
)
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
    summary_activities: Mapped[str] = mapped_column(String)
    accreditations: Mapped[Optional[dict]] = mapped_column(PickleType, nullable=True)
    max_publication_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="company"
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

from app.models.conversation_models import Conversation