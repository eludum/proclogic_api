import asyncio
import logging
from typing import Any
from sys import stdout

from fastapi import FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from fastapi_pagination import add_pagination

from app.config.settings import settings
from app.mcp.server import MOUNT_PATH as MCP_MOUNT_PATH
from app.mcp.server import build_asgi_app as build_mcp_app
from app.mcp.server import mcp_lifespan
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


# Error reporting is log-based: there is no hosted tracker or APM agent. Every
# error line goes to stdout, where the deployment's log pipeline collects it and
# alerts on error/exception/traceback matches. See the exception handler
# registered on the app below, which guarantees every unhandled request
# exception is logged at ERROR level with a full traceback.
logger = logging.getLogger("proclogic")


HEARTBEAT_MARKER = "proclogic alive"


async def _log_heartbeat() -> None:
    """Emit one line per ``log_heartbeat_seconds`` so the Loki stream exists.

    proclogic is quiet by design: it logs on error or on pod start and otherwise
    says nothing for up to 44 hours at a stretch. That made a broken log pipeline
    indistinguishable from a healthy idle app, so the alert rule watching for its
    absence had to sit at a useless 72h window. One line on an interval turns
    "no proclogic logs" into an alertable condition at 2h instead.

    Logged through a dedicated logger with an EXPLICIT level, which matters here:

    - ``basicConfig`` above pins the root logger to ERROR in production, so a
      plain ``logging.info``/``warning`` call would be dropped before reaching a
      handler.
    - ``alembic/env.py`` calls ``fileConfig(alembic.ini)`` during
      ``run_migration()``, which re-points the root logger at WARNING and
      disables every logger that already existed. Creating this logger inside the
      coroutine (i.e. after migrations have run) and clearing ``disabled`` keeps
      the heartbeat working on either side of that.

    A record only has to pass its own logger's level to reach the root handlers —
    the root logger's level is not re-checked on propagation — so INFO here ships
    regardless of what root is set to. INFO, deliberately: WARNING or above would
    have to be excluded by hand from ProclogicErrorOccurred.
    """
    interval = settings.log_heartbeat_seconds
    if interval <= 0:
        return

    heartbeat_logger = logging.getLogger("proclogic.heartbeat")
    heartbeat_logger.disabled = False
    heartbeat_logger.setLevel(logging.INFO)

    mode = "scraper" if settings.scraper_mode else "api"
    while True:
        heartbeat_logger.info("%s: mode=%s", HEARTBEAT_MARKER, mode)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run database migrations on startup
    logging.info("Running database migrations...")
    try:
        run_migration()
        logging.info("Database migrations completed successfully")
    except Exception as e:
        logging.error(f"Migration failed: {str(e)}")
        # Continue startup even if migrations fail (they might already be applied)

    # Pre-warm JWKS cache for faster first request
    from app.util.clerk import warm_jwks_cache
    await warm_jwks_cache()

    # Started for BOTH deployments. The scraper runs this same image with
    # scraper_mode=True, so it gets its own liveness signal for free — worth
    # having, since the scraper is the pod that has actually been OOM-killed.
    heartbeat_task = asyncio.create_task(_log_heartbeat())

    # Runs the MCP session manager for the lifetime of the app. A no-op when MCP
    # is disabled or the package is missing, so no branch is needed here.
    async with mcp_lifespan():
        try:
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
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)


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

# The MCP server, exposing the procurement database as tools for any MCP client.
# Its ASGI app authenticates every request with the same Clerk bearer token the
# REST API requires -- this URL is on the public internet.
if settings.mcp_enabled:
    _mcp_app = build_mcp_app()
    if _mcp_app is not None:
        proclogic.mount(MCP_MOUNT_PATH, _mcp_app)

# Configure CORS with specific origins to avoid preflight overhead
origins = [
    "http://localhost:3000",
    "https://app.proclogic.be",
    "https://proclogic.be",
]

proclogic.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


@proclogic.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log unhandled exceptions to stdout so the log pipeline captures them and
    can alert on them. Returns a generic 500 so internals are never leaked to
    the client."""
    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
