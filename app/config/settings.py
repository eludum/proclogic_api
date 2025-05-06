from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    scraper_mode: bool = False
    debug_mode: bool = False

    openai_api_key: str
    deepseek_api_key: Optional[str] = None

    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_server: str
    pubproc_token_url: str

    stripe_secret_key: str
    stripe_webhook_secret: str

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
