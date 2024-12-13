from sqlalchemy import JSON, Column, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Company(Base):
    __tablename__ = "companies"

    vat_number = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    sectors = Column(JSON, nullable=True)
    summary_activities = Column(String, nullable=True)
