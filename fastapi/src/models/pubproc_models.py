from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base
from typing import List, Optional

Base = declarative_base()


class Description(Base):
    __tablename__ = "descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    language: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)

    cpv_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("cpv_codes.id"))
    cpv_code: Mapped["CPVCode"] = relationship("CPVCode", back_populates="descriptions")

    dossier_id: Mapped[int] = mapped_column(Integer, ForeignKey("dossiers.id"))
    dossier: Mapped["Dossier"] = relationship("Dossier", back_populates="descriptions")

    lot_id: Mapped[int] = mapped_column(Integer, ForeignKey("lots.id"))
    lot: Mapped["Lot"] = relationship("Lot", back_populates="descriptions")


class CPVCode(Base):
    __tablename__ = "cpv_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, nullable=False)

    descriptions: Mapped[List[Description]] = relationship(
        "Description", back_populates="cpv_code"
    )


class EnterpriseCategory(Base):
    __tablename__ = "enterprise_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_code: Mapped[str] = mapped_column(String, nullable=False)
    levels: Mapped[List[int]] = mapped_column(JSON, default=[])

    # Add the foreign key reference to the Dossier table
    dossier_id: Mapped[int] = mapped_column(Integer, ForeignKey("dossiers.id"))

    # Relationship back to the Dossier model
    dossier: Mapped["Dossier"] = relationship("Dossier", back_populates="enterprise_categories")


class Dossier(Base):
    __tablename__ = "dossiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legal_basis: Mapped[str] = mapped_column(String, nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    procurement_procedure_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    reference_number: Mapped[str] = mapped_column(String, nullable=False)
    accreditations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    special_purchasing_technique: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )

    descriptions: Mapped[List[Description]] = relationship(
        "Description", back_populates="dossier"
    )

    # Update the relationship with the EnterpriseCategory model
    enterprise_categories: Mapped[List[EnterpriseCategory]] = relationship(
        "EnterpriseCategory", back_populates="dossier"
    )



class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reserved_execution: Mapped[List[str]] = mapped_column(JSON, default=[])
    reserved_participation: Mapped[List[str]] = mapped_column(JSON, default=[])

    # Foreign Key linking Lot to Publication
    publication_id: Mapped[int] = mapped_column(Integer, ForeignKey("publications.id"))

    # Relationship back to Publication
    publication: Mapped["Publication"] = relationship("Publication", back_populates="lots")

    descriptions: Mapped[List[Description]] = relationship(
        "Description", back_populates="lot"
    )



class OrganisationName(Base):
    __tablename__ = "organisation_names"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    language: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)

    organisation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organisations.id")
    )


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    tree: Mapped[str] = mapped_column(String, nullable=False)

    organisation_names: Mapped[List[OrganisationName]] = relationship(
        "OrganisationName", backref="organisation"
    )


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispatch_date: Mapped[str] = mapped_column(String, nullable=False)
    insertion_date: Mapped[str] = mapped_column(String, nullable=False)
    procedure_id: Mapped[str] = mapped_column(String, nullable=False)
    publication_date: Mapped[str] = mapped_column(String, nullable=False)
    publication_type: Mapped[str] = mapped_column(String, nullable=False)
    publication_workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    ted_published: Mapped[bool] = mapped_column(Boolean, nullable=False)

    cpv_main_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("cpv_codes.id"))
    cpv_main_code: Mapped[CPVCode] = relationship("CPVCode")

    # Relationship with Lot
    lots: Mapped[List[Lot]] = relationship("Lot", back_populates="publication")

    natures: Mapped[List[str]] = mapped_column(JSON, default=[])
    notice_ids: Mapped[List[str]] = mapped_column(JSON, default=[])
