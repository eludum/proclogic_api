from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Table, create_engine)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

# database.build

Base = declarative_base()

# Association tables for many-to-many relationships
publication_language_association = Table(
    'publication_language_association', Base.metadata,
    Column('publication_id', Integer, ForeignKey('publications.id')),
    Column('language', String)
)

nuts_code_association = Table(
    'nuts_code_association', Base.metadata,
    Column('publication_id', Integer, ForeignKey('publications.id')),
    Column('nuts_code', String)
)

notice_id_association = Table(
    'notice_id_association', Base.metadata,
    Column('publication_id', Integer, ForeignKey('publications.id')),
    Column('notice_id', String)
)


class OrganisationName(Base):
    __tablename__ = 'organisation_names'
    id = Column(Integer, primary_key=True)
    organisation_id = Column(Integer, ForeignKey('organisations.id'))
    text = Column(String)
    language = Column(String)


class Organisation(Base):
    __tablename__ = 'organisations'
    id = Column(Integer, primary_key=True)
    tree = Column(String)
    organisation_names = relationship(
        'OrganisationName', backref='organisation')


class Dossier(Base):
    __tablename__ = 'dossiers'
    id = Column(Integer, primary_key=True)
    titles = Column(JSONB)
    descriptions = Column(JSONB)
    accreditations = Column(JSONB)
    reference_number = Column(String)
    procurement_procedure_type = Column(String)
    special_purchasing_technique = Column(String)
    legal_basis = Column(String)


class Lot(Base):
    __tablename__ = 'lots'
    id = Column(Integer, primary_key=True)
    titles = Column(JSONB)
    descriptions = Column(JSONB)
    reserved_participation = Column(JSONB)
    reserved_execution = Column(JSONB)
    publication_id = Column(Integer, ForeignKey('publications.id'))


class CPVCode(Base):
    __tablename__ = 'cpv_codes'
    id = Column(Integer, primary_key=True)
    code = Column(String)
    descriptions = Column(JSONB)
    publication_id = Column(Integer, ForeignKey('publications.id'))


class Publication(Base):
    __tablename__ = 'publications'
    id = Column(Integer, primary_key=True)
    reference_number = Column(String)
    insertion_date = Column(DateTime)
    organisation_id = Column(Integer, ForeignKey('organisations.id'))
    cancelled_at = Column(DateTime)
    dossier_id = Column(Integer, ForeignKey('dossiers.id'))
    publication_workspace_id = Column(String)
    cpv_main_code_id = Column(Integer, ForeignKey('cpv_codes.id'))
    cpv_additional_codes = relationship('CPVCode', backref='publication')
    natures = Column(JSONB)
    publication_languages = relationship(
        'publication_language_association', backref='publication')
    nuts_codes = relationship('nuts_code_association', backref='publication')
    dispatch_date = Column(DateTime)
    sent_at = Column(JSONB)
    published_at = Column(JSONB)
    vault_submission_deadline = Column(DateTime)
    ted_published = Column(Boolean)
    notice_sub_type = Column(String)
    notice_ids = relationship('notice_id_association', backref='publication')
    procedure_id = Column(String)
    lots = relationship('Lot', backref='publication')

# Example engine creation
# engine = create_engine('postgresql://user:password@localhost/mydatabase')
# Base.metadata.create_all(engine)
