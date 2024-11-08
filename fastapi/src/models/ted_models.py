from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class Notice(Base):
    __tablename__ = 'notices'

    id = Column(Integer, primary_key=True)
    document_url_lot = Column(JSON)
    procedure_type = Column(String)
    classification_cpv = Column(JSON)
    publication_number = Column(String)
    contract_nature = Column(JSON)
    publication_date = Column(String)  # Using String to handle timezone
    links = Column(JSON)
    notice_title = Column(JSON)
    tender_value_cur = Column(JSON, nullable=True)
    tender_value = Column(JSON, nullable=True)
    organisation_contact_point_tenderer = Column(JSON, nullable=True)
