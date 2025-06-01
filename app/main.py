import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi_pagination import add_pagination

from app.config.settings import Settings
from app.routers.analytics import analytics_router
from app.routers.company import companies_router
from app.routers.conversations import conversations_router
from app.routers.health import health_router
from app.routers.kanban import kanban_router
from app.routers.notifications import notifications_router
from app.routers.publications import publications_router
from app.routers.users import users_router
from app.routers.stripe import stripe_router
from app.util.alembic_runner import run_migration
from app.util.pubproc import (
    fetch_pubproc_data,
    update_pubproc_data,
    gather_notifications,
)

settings = Settings()

logging.basicConfig(
    level=logging.INFO if settings.debug_mode else logging.ERROR,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.scraper_mode:
        # Create a list to track your background tasks
        # run_migration()
        background_tasks = []
        try:
            # Create individual tasks and track them in the list
            background_tasks.append(asyncio.create_task(fetch_pubproc_data()))
            background_tasks.append(asyncio.create_task(update_pubproc_data()))
            background_tasks.append(asyncio.create_task(gather_notifications()))

            # Yield control back to the application
            yield
        finally:
            # On shutdown, cancel all tasks and properly wait for them to complete
            for task in background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for all tasks to be cancelled properly
            if background_tasks:
                await asyncio.gather(*background_tasks, return_exceptions=True)
    else:
        # Make sure we always yield
        yield


proclogic = FastAPI(
    docs_url=None if not settings.debug_mode else "/docs",
    lifespan=lifespan,
    debug=settings.debug_mode,
)

security = HTTPBearer()

proclogic.include_router(health_router)

add_pagination(proclogic)
proclogic.include_router(publications_router)
proclogic.include_router(conversations_router)
proclogic.include_router(companies_router)
proclogic.include_router(users_router)
proclogic.include_router(analytics_router)
proclogic.include_router(notifications_router)
proclogic.include_router(kanban_router)
proclogic.include_router(stripe_router)

# TODO: fix cors
# origins = [
#     "http://localhost:3000",
#     settings.frontend_url,
# ]

proclogic.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
