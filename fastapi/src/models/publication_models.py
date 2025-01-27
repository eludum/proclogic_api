from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    PickleType,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Description(Base):
    __tablename__ = "descriptions"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text, unique=True)

    lot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lots.id"), nullable=True)

    dossier_reference_number: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dossiers.reference_number"), nullable=True
    )

    cpv_code_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cpv_codes.code"), nullable=True
    )


class CPVCode(Base):
    __tablename__ = "cpv_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    descriptions: Mapped[List["Description"]] = relationship()

    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id")
    )
    publication: Mapped["Publication"] = relationship(back_populates="cpv_main_code")

    # company_vat_number: Mapped[str] = mapped_column(ForeignKey("companies.vat_number"))


class Company(Base):
    __tablename__ = "companies"

    vat_number: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    # interested_cpv_codes: Mapped[List["CPVCode"]] = relationship()
    summary_activities: Mapped[str] = mapped_column(String)

    # publication_workspace_id: Mapped[str] = mapped_column(
    #     ForeignKey("publications.publication_workspace_id")
    # )


class EnterpriseCategory(Base):
    __tablename__ = "enterprise_categories"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    category_code: Mapped[str] = mapped_column(String)
    levels: Mapped[List[int]] = mapped_column(PickleType)

    dossier_reference_number: Mapped[str] = mapped_column(
        ForeignKey("dossiers.reference_number")
    )


class Dossier(Base):
    __tablename__ = "dossiers"

    reference_number: Mapped[str] = mapped_column(String, primary_key=True)
    accreditations: Mapped[Optional[dict]] = mapped_column(PickleType, nullable=True)
    legal_basis: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    procurement_procedure_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    special_purchasing_technique: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )

    descriptions: Mapped[List["Description"]] = relationship()
    titles: Mapped[List["Description"]] = relationship()
    enterprise_categories: Mapped[List["EnterpriseCategory"]] = relationship()

    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id")
    )
    publication: Mapped["Publication"] = relationship(back_populates="dossier")


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    reserved_execution: Mapped[List[str]] = mapped_column(ARRAY(String))
    reserved_participation: Mapped[List[str]] = mapped_column(ARRAY(String))

    descriptions: Mapped[List["Description"]] = relationship()
    titles: Mapped[List["Description"]] = relationship()

    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id")
    )


class OrganisationName(Base):
    __tablename__ = "organisation_names"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)

    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisations.organisation_id")
    )


class Organisation(Base):
    __tablename__ = "organisations"

    organisation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tree: Mapped[str] = mapped_column(String)

    organisation_names: Mapped[List["OrganisationName"]] = relationship()

    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id")
    )
    publication: Mapped["Publication"] = relationship(back_populates="organisation")


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
    vault_submission_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cpv_main_code: Mapped["CPVCode"] = relationship(back_populates="publication")
    dossier: Mapped["Dossier"] = relationship(back_populates="publication")
    organisation: Mapped["Organisation"] = relationship(back_populates="publication")

    cpv_additional_codes: Mapped[List["CPVCode"]] = relationship()
    lots: Mapped[List["Lot"]] = relationship()
    # recommended: Mapped[List["Company"]] = relationship()
