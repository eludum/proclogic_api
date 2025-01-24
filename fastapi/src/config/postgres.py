from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config.settings import Settings

settings = Settings()

engine = create_async_engine(
    settings.postgres_con_url,
    echo=True,
)

Base = declarative_base()

@asynccontextmanager
async def get_session():
    try:
        async_session = sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            yield session
    except:
        await session.rollback()
        raise
    finally:
        await session.close()
