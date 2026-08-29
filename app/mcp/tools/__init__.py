"""Importing this package registers every tool.

Import order is irrelevant except for the SQL tools, which register themselves
conditionally at the end (see app/mcp/tools/sql.py).
"""

from app.mcp.tools import awards, entities, publications  # noqa: F401
from app.mcp.tools.sql import register_sql_tools

register_sql_tools()
