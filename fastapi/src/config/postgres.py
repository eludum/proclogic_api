from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config.settings import Settings


settings = Settings


def async_session_generator():

    print(settings)

    engine = create_async_engine(
        settings.postgres_con_url,
        echo=True,
        future=True,
    )

    return sessionmaker(engine, class_=AsyncSession)


@asynccontextmanager
async def get_sql():
    try:
        async_session = async_session_generator()

        async with async_session() as session:
            yield session
    except:
        await session.rollback()
        raise
    finally:
        await session.close()
