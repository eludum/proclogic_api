import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from clerk_backend_api.jwks_helpers import authenticate_request

from app.config.settings import Settings
from app.routers.company import companies_router
from app.routers.email import email_router
from app.routers.health import health_router
from app.routers.publications import publications_router
from app.routers.conversations import conversations_router
from app.util.alembic_runner import run_migration
from app.util.pubproc import fetch_pubproc_data


settings = Settings()

logging.basicConfig(handlers=[logging.StreamHandler()])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: uncomment for prod
    # run_migration()
    task = asyncio.create_task(fetch_pubproc_data())
    yield
    task.cancel()

proclogic = FastAPI(lifespan=lifespan, debug=settings.fastapi_debug)

security = HTTPBearer()

proclogic.include_router(health_router)
proclogic.include_router(publications_router)
proclogic.include_router(conversations_router)
proclogic.include_router(companies_router)
proclogic.include_router(email_router)


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
