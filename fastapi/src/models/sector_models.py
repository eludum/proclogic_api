from sqlalchemy import JSON, Column, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Sector(Base):
    __tablename__ = "sectors"

    int = Column(id, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    sectors = Column(JSON, nullable=True)
    summary_activities = Column(String, nullable=True)
