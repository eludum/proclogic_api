from sqlalchemy import (JSON, Column, DateTime, Float, ForeignKey, Integer,
                        String, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class Notice(Base):
    __tablename__ = 'notices'

    id = Column(Integer, primary_key=True)
    document_url_lot = Column(JSON, nullable=True)
    procedure_type = Column(String, nullable=True)
    classification_cpv = Column(JSON, nullable=True)
    publication_number = Column(String, nullable=True)
    contract_nature = Column(JSON, nullable=True)
    publication_date = Column(String, nullable=True)  # Using String to handle timezone
    links = Column(JSON, nullable=True)
    notice_title = Column(JSON, nullable=True)
    tender_value_cur = Column(JSON, nullable=True)
    tender_value = Column(JSON, nullable=True)
    organisation_contact_point_tenderer = Column(JSON, nullable=True)
