"""Read-only SQL over the procurement tables.

This is what makes "the AI has access to the database" true rather than
approximate: it lets the model answer questions nobody wrote a tool for. It is
also the single most dangerous thing in this package, so it is defended twice.

**The real boundary is the database grant.** ``postgres_ro_con_url`` must point
at a role with SELECT on the procurement tables and nothing else -- no write
privileges anywhere, and no access at all to the per-tenant tables listed in
BLOCKED_TABLES. If that URL is unset the tool is never registered; it must never
fall back to the application's read-write engine.

**The parser below is defence in depth, not the boundary.** It rejects obvious
abuse early and gives the model a useful error message, but it is a string
check, and string checks lose. Do not weaken the grants on the strength of it.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config.settings import settings
from app.mcp.context import ToolContext
from app.mcp.registry import register

logger = logging.getLogger(__name__)

# Tables the model may read. Everything about public procurement notices and
# awards -- all of it public information published by the Belgian authorities.
ALLOWED_TABLES = {
    "publications",
    "contracts",
    "contract_organizations",
    "contract_addresses",
    "contract_contact_persons",
    "descriptions",
    "dossiers",
    "lots",
    "cpv_codes",
    "organisations",
    "organisation_names",
    "enterprise_categories",
    "publication_cpv_additional_codes",
    "publication_lots",
}

# Per-tenant data. Never reachable, by any caller, through this tool.
BLOCKED_TABLES = {
    "companies",
    "company_users",
    "sectors",
    "conversations",
    "messages",
    "emails",
    "email_events",
    "contract_email_tracking",
    "kanban_columns",
    "kanban_cards",
    "publication_statuses",
    "notifications",
    "company_publication_matches",
    "alembic_version",
}

_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"copy|vacuum|analyze|reindex|cluster|refresh|call|do|"
    r"pg_read_file|pg_read_binary_file|pg_ls_dir|pg_sleep|lo_import|lo_export|"
    r"dblink|pg_stat_file|current_setting|set_config|pg_terminate_backend"
    r")\b",
    re.IGNORECASE,
)

_COMMENT = re.compile(r"(--[^\n]*)|(/\*.*?\*/)", re.DOTALL)
_IDENTIFIER = re.compile(r"\b(?:from|join|into|update)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", re.IGNORECASE)

_ro_engine: Optional[Engine] = None


class SqlRejected(ValueError):
    """The query was refused before it reached the database."""


def _strip_comments(sql: str) -> str:
    return _COMMENT.sub(" ", sql)


def validate_sql(sql: str) -> str:
    """Return the cleaned query, or raise SqlRejected explaining why not."""
    if not sql or not sql.strip():
        raise SqlRejected("Empty query.")

    cleaned = _strip_comments(sql).strip().rstrip(";").strip()

    if ";" in cleaned:
        raise SqlRejected(
            "Only a single statement is allowed; remove the ';' and everything after it."
        )

    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SqlRejected("Only SELECT (or WITH ... SELECT) queries are allowed.")

    forbidden = _FORBIDDEN.search(cleaned)
    if forbidden:
        raise SqlRejected(
            f"'{forbidden.group(1)}' is not permitted. This connection is read-only."
        )

    for match in _IDENTIFIER.finditer(cleaned):
        table = match.group(1).split(".")[-1].strip('"').lower()
        if table in BLOCKED_TABLES:
            raise SqlRejected(
                f"Table '{table}' holds customer data and is not readable. "
                f"Readable tables: {', '.join(sorted(ALLOWED_TABLES))}."
            )

    return cleaned


def get_readonly_engine() -> Optional[Engine]:
    """Lazily build the read-only engine. None when not configured."""
    global _ro_engine
    if _ro_engine is not None:
        return _ro_engine

    url = settings.postgres_ro_con_url
    if not url:
        return None

    _ro_engine = create_engine(
        url,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={
            "connect_timeout": 10,
            "options": f"-c statement_timeout={settings.mcp_sql_statement_timeout_ms}",
        },
    )
    return _ro_engine


def sql_tool_available() -> bool:
    return bool(settings.mcp_sql_tool_enabled and settings.postgres_ro_con_url)


def describe_schema(ctx: ToolContext) -> Dict[str, Any]:
    """Columns of the readable tables, from the live catalogue."""
    engine = get_readonly_engine()
    if engine is None:
        return {"available": False, "reason": "Read-only database access is not configured."}

    query = text(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(:tables)
        ORDER BY table_name, ordinal_position
        """
    )

    tables: Dict[str, List[Dict[str, str]]] = {}
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        for row in connection.execute(query, {"tables": sorted(ALLOWED_TABLES)}):
            tables.setdefault(row.table_name, []).append(
                {"column": row.column_name, "type": row.data_type}
            )

    return {
        "available": True,
        "tables": tables,
        "notes": [
            "Award/gunning rows are publications where contract_id IS NOT NULL.",
            "A tender is open when vault_submission_deadline is in the future.",
            "Titles and descriptions live in `descriptions`, linked via "
            "dossiers.reference_number or lots.id -- not on publications.",
            "publications.searchable_content is a flattened copy of all that "
            "text; to_tsvector('dutch', searchable_content) is indexed.",
            "Customer-owned tables are not readable and are omitted here.",
        ],
    }


def run_sql_readonly(ctx: ToolContext, sql: str) -> Dict[str, Any]:
    """Execute one read-only SELECT and return at most mcp_sql_row_limit rows."""
    engine = get_readonly_engine()
    if engine is None:
        return {"error": "Read-only database access is not configured."}

    try:
        cleaned = validate_sql(sql)
    except SqlRejected as exc:
        return {"error": str(exc)}

    limit = settings.mcp_sql_row_limit
    # Wrapping rather than appending: an inner LIMIT or ORDER BY stays intact,
    # and the caller cannot dodge the cap by writing their own.
    wrapped = text(f"SELECT * FROM ({cleaned}) AS _mcp_query LIMIT {limit + 1}")

    logger.info(
        "run_sql_readonly user=%s company=%s sql=%s",
        ctx.user_id,
        ctx.company_vat,
        cleaned.replace("\n", " ")[:1000],
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            result = connection.execute(wrapped)
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchmany(limit + 1)]
    except Exception as exc:
        # The message is handed back to the model so it can correct itself; it
        # comes from Postgres and describes SQL, not internals worth hiding.
        logger.warning("run_sql_readonly failed: %s", exc)
        return {"error": f"Query failed: {str(exc)[:500]}"}

    truncated = len(rows) > limit
    return {
        "columns": columns,
        "row_count": min(len(rows), limit),
        "truncated": truncated,
        "rows": rows[:limit],
        **(
            {
                "note": (
                    f"More than {limit} rows matched; only the first {limit} are "
                    "shown. Add a LIMIT or aggregate instead of listing."
                )
            }
            if truncated
            else {}
        ),
    }


def register_sql_tools() -> None:
    """Register the SQL tools, but only when a read-only connection exists.

    Called at import time by app/mcp/tools/__init__.py. Registering
    unconditionally and erroring at call time would advertise a capability the
    deployment does not have, which just teaches the model to keep retrying.
    """
    if not sql_tool_available():
        logger.info(
            "SQL tools not registered: mcp_sql_tool_enabled=%s, read-only URL set=%s",
            settings.mcp_sql_tool_enabled,
            bool(settings.postgres_ro_con_url),
        )
        return

    register(
        name="describe_schema",
        description=(
            "List the database tables and columns you may query with "
            "run_sql_readonly. Call this before writing SQL."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    )(describe_schema)

    register(
        name="run_sql_readonly",
        description=(
            "Run one read-only SQL SELECT against the procurement database. Use "
            "it for questions the other tools cannot express -- cross-cutting "
            "aggregates, unusual groupings. Call describe_schema first. Prefer "
            "aggregates over listing rows; results are capped."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "A single SELECT (or WITH ... SELECT) statement. No "
                        "semicolons, no DDL or DML."
                    ),
                }
            },
            "required": ["sql"],
        },
    )(run_sql_readonly)
