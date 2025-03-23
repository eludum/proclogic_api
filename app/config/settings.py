from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    scraper_mode: bool = False
    openai_api_key: str
    deepseek_api_key: Optional[str] = None
    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_server: str
    pubproc_token_url: str
    clerk_secret_key: str
    clerk_jwks_url: str = (
        "https://clerk.proclogic.be/.well-known/jwks.json"
    )
    path_sea_api: str = "/api/eProcurementSea/v1"
    path_loc_api: str = "/api/eProcurementLoc/v1"
    path_dos_api: str = "/api/eProcurementDos/v1"
    pubproc_token: str = ""
    pubproc_token_exp: str = ""
    postgres_con_url: str
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_agent_ttl: int = 86400  # Default TTL for agent data (24 hours)
    template_folder: str = "email_template"
    mail_username: Optional[str] = ""
    mail_password: Optional[str] = ""
    mail_from: str = "info@proclogic.be"
    frontend_url: str = "https://app.proclogic.be"

    debug_mode: bool = False
    
    prefered_languages_descriptions: List[str] = ["NL", "EN", "FR"]
    openai_vector_store_accepted_formats: List[str] = [
        "c",
        "cpp",
        "css",
        "csv",
        "doc",
        "docx",
        "gif",
        "go",
        "html",
        "java",
        "jpeg",
        "jpg",
        "js",
        "json",
        "md",
        "pdf",
        "php",
        "pkl",
        "png",
        "pptx",
        "py",
        "rb",
        "tar",
        "tex",
        "ts",
        "txt",
        "webp",
        # "xlsx",
        "xml",
        "zip",
    ]

    class Config:
        env_file = ".env.prod", ".env"
        env_file_encoding = "utf-8"
