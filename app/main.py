import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi_pagination import add_pagination
import uvicorn

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
from app.routers.stripe import stripe_router
from app.util.alembic_runner import run_migration
from app.util.pubproc import fetch_pubproc_data, update_pubproc_data, gather_notifications

settings = Settings()

# Custom logging setup to filter out health checks
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        # Filter out logs related to health check endpoint
        return 'GET /health' not in record.getMessage()

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO if settings.debug_mode else logging.ERROR)

# Configure uvicorn and FastAPI loggers
for logger_name in ['uvicorn', 'uvicorn.access', 'fastapi']:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO if settings.debug_mode else logging.ERROR)
    # Add filter to remove health check logs
    logger.addFilter(HealthCheckFilter())

# Create console handler with formatting
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
root_logger.addHandler(console_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.scraper_mode:
        # Create a list to track your background tasks
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


proclogic = FastAPI(docs_url=None if not settings.debug_mode else "/docs", lifespan=lifespan, debug=settings.debug_mode)

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
proclogic.include_router(stripe_router)

proclogic.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
