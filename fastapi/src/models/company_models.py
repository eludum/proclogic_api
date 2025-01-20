from sqlalchemy import Table, Column, Integer, String, JSON, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base
from typing import List, Optional

Base = declarative_base()

# Association table for the many-to-many relationship between Company and Sector
company_sectors = Table(
    "company_sectors",
    Base.metadata,
    Column("company_vat_number", String, ForeignKey("companies.vat_number")),
    Column("sector_id", Integer, ForeignKey("sectors.id")),
)


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    codes: Mapped[List[str]] = mapped_column(JSON, default=[])

    # Define the relationship back to the Company model
    companies: Mapped[List["Company"]] = relationship(
        "Company", secondary=company_sectors, back_populates="interessed_sectors"
    )


class Company(Base):
    __tablename__ = "companies"

    vat_number: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    summary_activities: Mapped[str] = mapped_column(String, nullable=False)

    # Define the relationship to the Sector model
    interessed_sectors: Mapped[List[Sector]] = relationship(
        "Sector", secondary=company_sectors, back_populates="companies"
    )
