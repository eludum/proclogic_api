import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi_pagination import add_pagination
from fastapi_pagination.utils import disable_installed_extensions_check

from app.config.settings import Settings
from app.routers.analytics import analytics_router
from app.routers.company import companies_router
from app.routers.conversations import conversations_router
from app.routers.email import email_router
from app.routers.health import health_router
from app.routers.kanban import kanban_router
from app.routers.notifications import notifications_router
from app.routers.publications import publications_router
from app.routers.users import users_router
from app.util.alembic_runner import run_migration
from app.util.pubproc import fetch_pubproc_data

settings = Settings()

logging.basicConfig(
    level=logging.INFO if settings.debug_mode else logging.ERROR,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    disable_installed_extensions_check()
    # TODO: add ratelimiter
    if settings.scraper_mode:
        run_migration()
        task = asyncio.create_task(fetch_pubproc_data())
        yield
        task.cancel()
    else:
        # Make sure we always yield
        yield


proclogic = FastAPI(lifespan=lifespan, debug=settings.debug_mode)

security = HTTPBearer()

proclogic.include_router(health_router)

add_pagination(proclogic)
proclogic.include_router(publications_router)
proclogic.include_router(conversations_router)
proclogic.include_router(companies_router)
proclogic.include_router(users_router)
proclogic.include_router(analytics_router)
proclogic.include_router(notifications_router)
proclogic.include_router(email_router)
proclogic.include_router(kanban_router)

if settings.debug_mode:
    origins = [
        "http://localhost:3000",
    ]

    proclogic.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
