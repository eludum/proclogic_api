"""Calling tools.

Two transports, one registry:

  * ``inprocess`` (default) dispatches straight to the handler. This is the
    production path: Procy and the retrieval agent run inside the same process
    as the MCP server, and making the API issue an authenticated HTTP request to
    itself once per tool call -- inside a websocket stream, several times per
    message -- would buy nothing.

  * ``http`` drives a real MCP client session against /mcp. Same registry, same
    handlers, but over the wire, so it exercises exactly what an external MCP
    client sees. Useful for verifying the server rather than for serving users.

Handlers are synchronous and open their own database sessions, so the async
entry point hands them to a worker thread. That is not incidental: this codebase
has a load-bearing rule that blocking work never runs on the event loop.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.mcp.context import ANONYMOUS, ToolContext
from app.mcp.registry import call_tool as _call_tool_sync
from app.mcp.registry import serialise_result

logger = logging.getLogger(__name__)

MCP_MOUNT_PATH = "/mcp"


def call_tool_sync(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    ctx: Optional[ToolContext] = None,
) -> Any:
    return _call_tool_sync(name, arguments, ctx or ANONYMOUS)


async def _call_over_http(
    name: str, arguments: Dict[str, Any], ctx: ToolContext
) -> Any:
    """Round-trip a tool call through the mounted MCP server."""
    token = settings.mcp_service_token
    if not token:
        logger.warning(
            "mcp_transport is 'http' but mcp_service_token is unset; "
            "falling back to in-process dispatch."
        )
        return await asyncio.to_thread(call_tool_sync, name, arguments, ctx)

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = f"http://127.0.0.1:8000{MCP_MOUNT_PATH}"
    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)

    # MCP returns content blocks; our tools always emit a single JSON text block.
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


async def call_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    ctx: Optional[ToolContext] = None,
) -> Any:
    """Invoke a tool from async code, off the event loop."""
    context = ctx or ANONYMOUS
    args = arguments or {}

    if settings.mcp_transport == "http":
        return await _call_over_http(name, args, context)

    return await asyncio.to_thread(call_tool_sync, name, args, context)


async def call_tool_as_text(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    ctx: Optional[ToolContext] = None,
) -> str:
    """Invoke a tool and render the result for a model's tool message.

    Errors come back as JSON rather than raising. A failed tool call should
    leave the model able to try something else, not tear down the whole turn --
    but it must be able to *see* that the call failed, so failures are explicit
    in the payload rather than an empty result.
    """
    try:
        result = await call_tool(name, arguments, ctx)
    except KeyError:
        logger.warning("Model called unknown tool %r", name)
        return json.dumps({"error": f"Unknown tool '{name}'."})
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        logger.error("Tool %s raised: %s", name, exc, exc_info=exc)
        return json.dumps(
            {"error": f"Tool '{name}' failed: {str(exc)[:300]}"}
        )

    return serialise_result(name, result)
