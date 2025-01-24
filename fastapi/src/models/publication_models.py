from typing import List, Optional
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    PickleType,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    pass


# Association table for the many-to-many relationship between Company and Sector
company_sectors = Table(
    "company_sectors",
    Base.metadata,
    Column(
        "company_vat_number",
        String,
        ForeignKey("companies.vat_number"),
        primary_key=True,
    ),
    Column("sector_name", String, ForeignKey("sectors.name"), primary_key=True),
)


class Description(Base):
    __tablename__ = "descriptions"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)

    cpv_code_code: Mapped[Optional[str]] = mapped_column(ForeignKey("cpv_codes.code"))
    dossier_reference_number: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dossiers.reference_number")
    )
    lot_id: Mapped[Optional[str]] = mapped_column(ForeignKey("lots.id"))


class CPVCode(Base):
    __tablename__ = "cpv_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)

    descriptions: Mapped[List[Description]] = relationship()
    sector_name: Mapped[Optional[str]] = mapped_column(ForeignKey("sectors.name"))


class Sector(Base):
    __tablename__ = "sectors"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    cpv_codes: Mapped[List[CPVCode]] = relationship()


class Company(Base):
    __tablename__ = "companies"

    vat_number: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    sectors: Mapped[List[Sector]] = relationship(secondary=company_sectors)
    summary_activities: Mapped[str] = mapped_column(String)

    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id")
    )


class EnterpriseCategory(Base):
    __tablename__ = "enterprise_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_code: Mapped[str] = mapped_column(String)
    levels: Mapped[List[int]] = mapped_column(ARRAY(Integer))

    dossier_reference_number: Mapped[str] = mapped_column(
        ForeignKey("dossiers.reference_number")
    )


class Dossier(Base):
    __tablename__ = "dossiers"

    reference_number: Mapped[str] = mapped_column(String, primary_key=True)
    accreditations: Mapped[Optional[dict]] = mapped_column(PickleType, nullable=True)
    legal_basis: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    procurement_procedure_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    special_purchasing_technique: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    descriptions: Mapped[List[Description]] = relationship(overlaps="titles")
    titles: Mapped[List[Description]] = relationship(overlaps="descriptions")
    enterprise_categories: Mapped[List[EnterpriseCategory]] = relationship()


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    reserved_execution: Mapped[List[str]] = mapped_column(ARRAY(String))
    reserved_participation: Mapped[List[str]] = mapped_column(ARRAY(String))

    descriptions: Mapped[List[Description]] = relationship(overlaps="titles")
    titles: Mapped[List[Description]] = relationship(overlaps="descriptions")

    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id")
    )


class OrganisationName(Base):
    __tablename__ = "organisation_names"

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)

    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisations.organisation_id")
    )


class Organisation(Base):
    __tablename__ = "organisations"

    organisation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tree: Mapped[str] = mapped_column(String)

    organisation_names: Mapped[List[OrganisationName]] = relationship()


class Publication(Base):
    __tablename__ = "publications"

    publication_workspace_id: Mapped[str] = mapped_column(String, primary_key=True)

    dispatch_date: Mapped[datetime] = mapped_column(DateTime)
    insertion_date: Mapped[datetime] = mapped_column(DateTime)
    natures: Mapped[List[str]] = mapped_column(ARRAY(String))
    notice_ids: Mapped[List[str]] = mapped_column(ARRAY(String))
    notice_sub_type: Mapped[str] = mapped_column(String)
    nuts_codes: Mapped[List[str]] = mapped_column(ARRAY(String))
    procedure_id: Mapped[str] = mapped_column(String)
    publication_date: Mapped[datetime] = mapped_column(DateTime)
    publication_languages: Mapped[List[str]] = mapped_column(ARRAY(String))
    publication_reference_numbers_bda: Mapped[List[str]] = mapped_column(ARRAY(String))
    publication_reference_numbers_ted: Mapped[List[str]] = mapped_column(ARRAY(String))
    publication_type: Mapped[str] = mapped_column(String)
    published_at: Mapped[List[datetime]] = mapped_column(ARRAY(DateTime))
    reference_number: Mapped[str] = mapped_column(String)
    sent_at: Mapped[List[datetime]] = mapped_column(ARRAY(DateTime))
    ted_published: Mapped[bool] = mapped_column(Boolean)
    vault_submission_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    
    cpv_additional_codes: Mapped[List[CPVCode]] = relationship(overlaps="cpv_main_code")
    cpv_main_code_id: Mapped[str] = mapped_column(ForeignKey("cpv_codes.code"))
    cpv_main_code: Mapped[CPVCode] = relationship(overlaps="cpv_additional_codes")

    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossiers.reference_number"))
    dossier: Mapped[Dossier] = relationship()
    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisations.organisation_id")
    )
    organisation: Mapped[Organisation] = relationship()
    lots: Mapped[List[Lot]] = relationship()
    recommended: Mapped[Optional[List[Company]]] = relationship()
