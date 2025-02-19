from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    ForeignKey,
    Integer,
    PickleType,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.publication_models import publications_companies


class Sector(Base):
    __tablename__ = "sectors"
    # TODO: set constraint, avoid duplicates, worry about this when you have lots of clients...

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    sector: Mapped[str] = mapped_column(String)
    cpv_codes: Mapped[List[str]] = mapped_column(ARRAY(String))
    company_vat_number: Mapped[int] = mapped_column(
        ForeignKey("companies.vat_number")
    )


class Company(Base):
    __tablename__ = "companies"

    vat_number: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    accreditations: Mapped[Optional[dict]] = mapped_column(PickleType, nullable=True)
    max_publication_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interested_sectors: Mapped[List["Sector"]] = relationship()
    summary_activities: Mapped[str] = mapped_column(String)
    recommended_publications: Mapped[List["Publication"]] = relationship(
        secondary=publications_companies, back_populates="recommended_companies"
    )
