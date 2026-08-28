"""The MCP server mounted at /mcp.

Exposes the registry over Streamable HTTP so any MCP client -- the Inspector,
Claude Desktop, another service -- can query the procurement database with the
same tools Procy uses.

Authentication is not optional. api.proclogic.be is on the public internet and
these tools read a database, so every request must carry the same Clerk bearer
token the REST API requires. The verified identity becomes the ToolContext that
tenant-scoped tools filter on, which is why it is derived from the token and
attached to the ASGI scope rather than taken from anything a caller sends.
"""

import contextlib
import logging
from contextvars import ContextVar
from typing import Any, AsyncIterator, Optional

from app.config.settings import settings
from app.mcp.client import call_tool_as_text
from app.mcp.context import ANONYMOUS, ToolContext, build_context_async
from app.mcp.registry import all_tools

logger = logging.getLogger(__name__)

MOUNT_PATH = "/mcp"

# Key under which the authenticated ToolContext is stashed on the ASGI scope.
SCOPE_KEY = "proclogic_tool_context"

# Fallback path to the same value. The scope is the primary channel -- it is
# request-bound and cannot leak across concurrent requests -- but the transport
# does not attach the HTTP request to every handler invocation, so this covers
# the gap.
_current_context: ContextVar[ToolContext] = ContextVar(
    "mcp_tool_context", default=ANONYMOUS
)

_server = None
_asgi_app = None


def _context_from(request_ctx: Any) -> ToolContext:
    """Recover the caller's identity for one tool call."""
    request = getattr(request_ctx, "request", None)
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        ctx = scope.get(SCOPE_KEY)
        if isinstance(ctx, ToolContext):
            return ctx
    return _current_context.get()


def _build_server():
    """Construct the low-level MCP server.

    The tools carry hand-written JSON schemas -- their handlers take **params --
    so schema inference from a function signature would produce nothing useful.
    The handlers below therefore serve the registry directly.
    """
    import mcp.types as types
    from mcp.server.lowlevel import Server

    from app.mcp import load_tools

    load_tools()

    async def on_list_tools(request_ctx, params) -> "types.ListToolsResult":
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.parameters,
                )
                for tool in all_tools()
            ]
        )

    async def on_call_tool(request_ctx, params) -> "types.CallToolResult":
        ctx = _context_from(request_ctx)
        logger.info(
            "MCP tool call name=%s user=%s company=%s",
            params.name,
            ctx.user_id,
            ctx.company_vat,
        )
        payload = await call_tool_as_text(params.name, params.arguments or {}, ctx)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=payload)]
        )

    return Server(
        "proclogic",
        version="1.0.0",
        title="ProcLogic procurement data",
        instructions=(
            "Search Belgian public procurement: published tenders and awarded "
            "contracts (gunningen), with buyers, winners, values and dates. "
            "Call describe_schema before writing SQL."
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _authenticate(scope) -> Optional[ToolContext]:
    """Verify the bearer token on an ASGI request. None means reject."""
    from fastapi.security import HTTPAuthorizationCredentials

    from app.util.clerk import get_auth_user

    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    authorization = headers.get("authorization", "")

    if not authorization.lower().startswith("bearer "):
        return None

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        auth_user = await get_auth_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    except Exception as exc:
        logger.info("MCP authentication rejected: %s", exc)
        return None

    return await build_context_async(auth_user.user_id, auth_user.email)


async def _send_unauthorized(send) -> None:
    body = b'{"error":"Authentication required. Send a Clerk bearer token."}'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _transport_security():
    from mcp.server.transport_security import TransportSecuritySettings

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(settings.mcp_allowed_hosts),
        allowed_origins=list(settings.mcp_allowed_origins),
    )


def build_asgi_app():
    """The authenticated ASGI app to mount at /mcp, or None if unavailable."""
    global _server, _asgi_app

    if _asgi_app is not None:
        return _asgi_app

    try:
        _server = _build_server()
        inner = _server.streamable_http_app(
            # Mounted at /mcp by the parent app, so the inner route is the root.
            streamable_http_path="/",
            stateless_http=True,
            transport_security=_transport_security(),
        )
    except ImportError as exc:
        # The API must still boot without the mcp package; the tool layer works
        # in-process regardless of whether /mcp is served.
        logger.error("mcp package unavailable, /mcp will not be mounted: %s", exc)
        return None

    async def app(scope, receive, send):
        if scope["type"] != "http":
            await _send_unauthorized(send)
            return

        ctx = await _authenticate(scope)
        if ctx is None:
            await _send_unauthorized(send)
            return

        scope[SCOPE_KEY] = ctx
        token = _current_context.set(ctx)
        try:
            await inner(scope, receive, send)
        finally:
            _current_context.reset(token)

    _asgi_app = app
    return _asgi_app


@contextlib.asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Run the session manager for the lifetime of the app.

    streamable_http_app() returns a Starlette app whose own lifespan would do
    this, but a mounted sub-application's lifespan is never run by the parent --
    so without this the session manager is never started and every request to
    /mcp hangs.

    A no-op when MCP is disabled or the package is missing, so the caller does
    not need to branch.
    """
    if not settings.mcp_enabled or build_asgi_app() is None:
        yield
        return

    async with _server.session_manager.run():
        logger.info(
            "MCP server ready at %s with %d tools", MOUNT_PATH, len(all_tools())
        )
        yield
