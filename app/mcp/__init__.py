"""MCP data layer.

Deliberately free of top-level submodule imports: app.mcp.tools imports
app.mcp.registry, so importing the tools package from here would make importing
the registry circular. Call load_tools() instead, from wherever tools are first
needed.
"""

import logging

logger = logging.getLogger(__name__)

_tools_loaded = False


def load_tools() -> None:
    """Import the tool modules so they register themselves. Idempotent."""
    global _tools_loaded
    if _tools_loaded:
        return

    from app.mcp import tools  # noqa: F401  (import registers the tools)
    from app.mcp.registry import all_tools

    _tools_loaded = True
    logger.info("Registered %d MCP tools", len(all_tools()))
