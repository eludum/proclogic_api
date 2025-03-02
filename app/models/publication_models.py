from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PickleType,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


publication_cpv_additional_codes = Table(
    "publication_cpv_additional_codes",
    Base.metadata,
    Column(
        "publication_publication_workspace_id",
        ForeignKey("publications.publication_workspace_id"),
    ),
    Column("cpv_code_code", ForeignKey("cpv_codes.code")),
)


publication_lots = Table(
    "publication_lots",
    Base.metadata,
    Column(
        "publication_publication_workspace_id",
        ForeignKey("publications.publication_workspace_id"),
    ),
    Column("lot_id", ForeignKey("lots.id")),
)


publications_companies = Table(
    "publications_companies",
    Base.metadata,
    Column(
        "publication_publication_workspace_id",
        ForeignKey("publications.publication_workspace_id"),
    ),
    Column("company_vat_number", ForeignKey("companies.vat_number")),
)


class Description(Base):
    __tablename__ = "descriptions"
    # TODO: set constraint, avoid duplicates, worry about this when you have lots of clients...
    # __table_args__ = (
    #     Index("idx_text_language_hash", func.md5("text"), "language", unique=True),
    # )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)

    # Relationships with Lot
    lot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lots.id"), nullable=True)
    lot_descriptions: Mapped[Optional["Lot"]] = relationship(
        back_populates="descriptions", overlaps="lot_titles"
    )
    lot_titles: Mapped[Optional["Lot"]] = relationship(
        back_populates="titles", overlaps="lot_descriptions"
    )

    # Relationships with Dossier
    dossier_reference_number: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dossiers.reference_number"), nullable=True
    )
    dossier_descriptions: Mapped[Optional["Dossier"]] = relationship(
        back_populates="descriptions", overlaps="dossier_titles"
    )
    dossier_titles: Mapped[Optional["Dossier"]] = relationship(
        back_populates="titles", overlaps="dossier_descriptions"
    )

    # Relationship with CPVCode
    cpv_code_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cpv_codes.code"), nullable=True
    )
    cpv_code: Mapped[Optional["CPVCode"]] = relationship(back_populates="descriptions")


class CPVCode(Base):
    __tablename__ = "cpv_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    descriptions: Mapped[List["Description"]] = relationship(back_populates="cpv_code")


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

    # Relationships with Description
    descriptions: Mapped[List["Description"]] = relationship(
        back_populates="dossier_descriptions", overlaps="dossier_titles"
    )
    titles: Mapped[List["Description"]] = relationship(
        back_populates="dossier_titles", overlaps="descriptions,dossier_descriptions"
    )

    enterprise_categories: Mapped[List["EnterpriseCategory"]] = relationship()


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    reserved_execution: Mapped[List[str]] = mapped_column(ARRAY(String))
    reserved_participation: Mapped[List[str]] = mapped_column(ARRAY(String))

    # Relationships with Description
    descriptions: Mapped[List["Description"]] = relationship(
        back_populates="lot_descriptions", overlaps="lot_titles"
    )
    titles: Mapped[List["Description"]] = relationship(
        back_populates="lot_titles", overlaps="descriptions,lot_descriptions"
    )


class OrganisationName(Base):
    __tablename__ = "organisation_names"
    __table_args__ = (
        UniqueConstraint("text", "language", name="_text_language_uc_org_name"),
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String)

    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisations.organisation_id")
    )


class Organisation(Base):
    __tablename__ = "organisations"

    organisation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tree: Mapped[str] = mapped_column(String)

    organisation_names: Mapped[List["OrganisationName"]] = relationship()


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
    ai_summary_without_documents: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    ai_summary_with_documents: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    award: Mapped[Optional[dict]] = mapped_column(PickleType, nullable=True)

    cpv_main_code_code: Mapped[str] = mapped_column(ForeignKey("cpv_codes.code"))
    cpv_main_code: Mapped["CPVCode"] = relationship()
    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisations.organisation_id")
    )
    organisation: Mapped["Organisation"] = relationship()
    dossier_reference_number: Mapped[str] = mapped_column(
        ForeignKey("dossiers.reference_number")
    )
    dossier: Mapped["Dossier"] = relationship()

    cpv_additional_codes: Mapped[List["CPVCode"]] = relationship(
        secondary=publication_cpv_additional_codes
    )
    lots: Mapped[List["Lot"]] = relationship(secondary=publication_lots)
    recommended_companies: Mapped[List["Company"]] = relationship(
        secondary=publications_companies, back_populates="recommended_publications"
    )
    saved_companies: Mapped[List["Company"]] = relationship(
        secondary=publications_companies, back_populates="saved_publications"
    )
