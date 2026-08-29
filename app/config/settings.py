from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    scraper_mode: bool = False
    debug_mode: bool = False

    # Liveness canary for the log pipeline itself. proclogic only logs on error
    # or on pod start — 40 active hours out of 337 measured over 14 days, with
    # 44h stretches of legitimate silence — so "healthy and quiet" and "the log
    # path is broken" look identical from the outside. One line on this interval
    # gives koselogic_iac's ProclogicLogIngestAbsent rule something to miss.
    # 0 disables it.
    log_heartbeat_seconds: int = 1800

    openai_api_key: str
    openai_model: str = "gpt-5-mini"

    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_server: str
    pubproc_token_url: str

    stripe_secret_key: str
    stripe_webhook_secret: str

    mailtrap_token: str = ""

    clerk_secret_key: str
    clerk_jwks_url: str = "https://clerk.proclogic.be/.well-known/jwks.json"
    pubproc_token: str = ""
    pubproc_token_exp: str = ""
    path_sea_api: str = "/api/eProcurementSea/v1"
    path_loc_api: str = "/api/eProcurementLoc/v1"
    path_dos_api: str = "/api/eProcurementDos/v1"

    postgres_con_url: str
    redis_host: str = "proclogic-redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- MCP / AI data access -------------------------------------------------
    # The MCP server exposes the procurement database as tools. It is mounted at
    # /mcp for external clients, and the same tool registry backs Procy's chat
    # tool loop and the similar-awards retrieval agent.
    mcp_enabled: bool = True
    # "inprocess" dispatches straight to the handler; "http" drives a real MCP
    # client session against /mcp. Both go through the same registry, so "http"
    # exercises exactly what an external client sees.
    mcp_transport: str = "inprocess"
    # Bearer token used only when mcp_transport="http". Without it the http
    # transport cannot authenticate against /mcp and falls back to inprocess.
    mcp_service_token: str = ""
    # Hosts and origins the MCP transport will accept. The SDK enables DNS
    # rebinding protection by default and, left alone, would allow only
    # localhost -- which rejects every real request to api.proclogic.be.
    mcp_allowed_hosts: List[str] = [
        "api.proclogic.be",
        "localhost:*",
        "127.0.0.1:*",
    ]
    mcp_allowed_origins: List[str] = [
        "https://app.proclogic.be",
        "https://proclogic.be",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ]

    # Raw read-only SQL tool. Fails closed: without postgres_ro_con_url the tool
    # is never registered, so it can never fall back to the read-write engine.
    mcp_sql_tool_enabled: bool = True
    postgres_ro_con_url: Optional[str] = None
    mcp_sql_row_limit: int = 200
    mcp_sql_statement_timeout_ms: int = 5000

    # Retrieval agent caps. The agent may call tools this many times before it is
    # forced to answer, and may never consider more than max_candidates rows.
    retrieval_agent_max_rounds: int = 4
    retrieval_agent_max_candidates: int = 60
    retrieval_agent_timeout_seconds: float = 20.0
    # Ceiling for the opt-in deep search, which the user starts deliberately and
    # watches progress for. Measured at ~90s against production, so this leaves
    # room without letting a wedged run hold its lock all day.
    retrieval_agent_deep_timeout_seconds: float = 240.0
    # How many tool-calling rounds Procy may take before it must answer.
    chat_agent_max_rounds: int = 5
    # Messages of history replayed into a chat turn. Unbounded replay was
    # affordable when every turn was one call; with tool results in the loop
    # it is not.
    chat_history_max_messages: int = 30
    similar_awards_cache_ttl: int = 604800  # 7 days

    # Used to build absolute links when Procy cites a publication or a gunning.
    frontend_base_url: str = "https://app.proclogic.be"

    template_folder: str = "email_template"
    mail_username: Optional[str] = ""
    mail_password: Optional[str] = ""
    mail_from: str = "info@proclogic.be"

    prefered_languages_descriptions: List[str] = ["NL", "EN", "FR"]
    openai_vector_store_accepted_formats: List[str] = [
        ".c",
        ".cpp",
        ".cs",
        ".css",
        ".doc",
        ".docx",
        ".go",
        ".html",
        ".java",
        ".js",
        ".json",
        ".md",
        ".pdf",
        ".php",
        ".pptx",
        ".py",
        ".py",
        ".rb",
        ".sh",
        ".tex",
        ".ts",
        ".txt",
    ]


settings = Settings() # type: ignore
