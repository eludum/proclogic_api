from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    ForeignKey,
    Table,
    Boolean,
    DateTime,
    JSON,
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker

Base = declarative_base()


class Description(Base):
    __tablename__ = "descriptions"
    id = Column(Integer, primary_key=True)
    language = Column(String, nullable=False)
    text = Column(String, nullable=False)
    cpv_code_id = Column(Integer, ForeignKey("cpv_codes.id"))
    dossier_id = Column(Integer, ForeignKey("dossiers.id"))
    lot_id = Column(Integer, ForeignKey("lots.id"))
    title_id = Column(Integer, ForeignKey("titles.id"))


class CPVCode(Base):
    __tablename__ = "cpv_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False)
    descriptions = relationship("Description", backref="cpv_code")


class EnterpriseCategory(Base):
    __tablename__ = "enterprise_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_code = Column(String, nullable=False)
    levels = Column(String)  # Store levels as a comma-separated string


class Dossier(Base):
    __tablename__ = "dossiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    legal_basis = Column(String, nullable=False)
    number = Column(String, nullable=False)
    procurement_procedure_type = Column(String, nullable=False)
    reference_number = Column(String, nullable=False)
    descriptions = relationship("Description")
    enterprise_categories = relationship("EnterpriseCategory")


class Lot(Base):
    __tablename__ = "lots"
    id = Column(Integer, primary_key=True)
    descriptions = relationship("Description", backref="lot")
    reserved_execution = Column(JSON)
    reserved_participation = Column(JSON)
    titles = relationship("Description", backref="lot_title")


class OrganisationName(Base):
    __tablename__ = "organisation_names"
    id = Column(Integer, primary_key=True)
    language = Column(String, nullable=False)
    text = Column(String, nullable=False)
    organisation_id = Column(Integer, ForeignKey("organisations.id"))


class Organisation(Base):
    __tablename__ = "organisations"
    id = Column(Integer, primary_key=True)
    organisation_id = Column(Integer, nullable=False)
    organisation_names = relationship("OrganisationName", backref="organisation")
    tree = Column(String, nullable=False)


class Publication(Base):
    __tablename__ = "publications"
    id = Column(Integer, primary_key=True)
    cpv_additional_codes = relationship("CPVCode", backref="publication")
    cpv_main_code_id = Column(Integer, ForeignKey("cpv_codes.id"))
    dispatch_date = Column(String, nullable=False)
    dossier_id = Column(Integer, ForeignKey("dossiers.id"))
    insertion_date = Column(String, nullable=False)
    lots = relationship("Lot", backref="publication")
    natures = Column(JSON)
    notice_ids = Column(JSON)
    notice_sub_type = Column(String, nullable=False)
    nuts_codes = Column(JSON)
    organisation_id = Column(Integer, ForeignKey("organisations.id"))
    procedure_id = Column(String, nullable=False)
    publication_date = Column(String, nullable=False)
    publication_languages = Column(JSON)
    publication_reference_numbers_bda = Column(JSON)
    publication_reference_numbers_ted = Column(JSON)
    publication_type = Column(String, nullable=False)
    publication_workspace_id = Column(String, nullable=False)
    published_at = Column(JSON)
    reference_number = Column(String, nullable=False)
    sent_at = Column(JSON)
    ted_published = Column(Boolean, nullable=False)
    vault_submission_deadline = Column(String, nullable=False)


# Example usage
# engine = create_engine('postgresql://user:password@localhost/mydatabase')
# Base.metadata.create_all(engine)
