from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings

settings = Settings()

engine = create_engine(settings.postgres_con_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
