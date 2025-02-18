from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    deepseek_api_key: str
    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_server: str
    pubproc_token_url: str
    path_sea_api: str = "/api/eProcurementSea/v1"
    path_loc_api: str = "/api/eProcurementLoc/v1"
    path_dos_api: str = "/api/eProcurementDos/v1"
    pubproc_token: str = ""
    pubproc_token_exp: str = ""
    postgres_host: str = "localhost"
    postgres_con_url: str
    template_folder: str = "email_template"
    mail_username: str
    mail_password: str
    mail_from: str

    fastapi_debug: bool = True
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
