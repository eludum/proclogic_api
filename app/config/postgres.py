from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings

settings = Settings()

engine = create_engine(settings.postgres_con_url)

Session = sessionmaker(bind=engine)

def get_session():
    return Session()

def get_session_generator():
    session = Session()
    try:
        yield session
    finally:
        session.close()
