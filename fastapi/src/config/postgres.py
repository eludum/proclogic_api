from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import Settings

settings = Settings()

engine = create_engine(settings.postgres_con_url)

Session = sessionmaker(bind=engine)

def get_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()
