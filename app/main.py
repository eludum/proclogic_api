import asyncio
import logging
from typing import Any
import sentry_sdk
from sys import stdout

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi_pagination import add_pagination

from app.config.settings import settings
from app.routers.company import companies_router
from app.routers.conversations import conversations_router
from app.routers.health import health_router
from app.routers.kanban import kanban_router
from app.routers.notifications import notifications_router
from app.routers.publication_contracts import contracts_router
from app.routers.publications import publications_router
from app.routers.stripe import stripe_router
from app.routers.users import users_router
from app.routers.email import email_tracking_router
from app.util.alembic_runner import run_migration
from app.util.pubproc import (
    fetch_pubproc_data,
    gather_notifications,
    update_pubproc_data,
)


class EndpointFilter(logging.Filter):
    def __init__(
        self,
        path: str,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._path = path

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find(self._path) == -1


logging.basicConfig(
    level=(
        logging.INFO if settings.debug_mode else logging.ERROR
    ),  # change logging info to debug if you actually need to go deep
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(stdout)],
)


uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(EndpointFilter(path="/health"))


if settings.SENTRY_DSN and settings.debug_mode is not True:
    sentry_sdk.init(
        dsn=str(settings.SENTRY_DSN),
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # Set profile_session_sample_rate to 1.0 to profile 100%
        # of profile sessions.
        profile_session_sample_rate=1.0,
        # Set profile_lifecycle to "trace" to automatically
        # run the profiler on when there is an active transaction
        profile_lifecycle="trace",
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
proclogic.include_router(contracts_router)
proclogic.include_router(notifications_router)
proclogic.include_router(kanban_router)
proclogic.include_router(stripe_router)
proclogic.include_router(email_tracking_router)

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
