from openai import Client
from pydantic_settings import BaseSettings

from ai.deepseek import get_deepseek_client


class Settings(BaseSettings):
    openai_api_key: str
    deepseek_api_key: str
    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_server: str = "https://public.int.fedservices.be"
    pubproc_token_url: str = pubproc_server + "/api/oauth2/token"
    path_sea_api: str = "/api/eProcurementSea/v1"
    path_loc_api: str = "/api/eProcurementLoc/v1"
    path_dos_api: str = "/api/eProcurementDos/v1"
    pubproc_token: str = ""
    pubproc_token_exp: str = ""
    redis_host: str = "localhost"
    postgres_host: str = "localhost"
    postgres_con_url: str = ""
    template_folder: str = "email_template"
    mail_username: str
    mail_password: str
    mail_from: str
    debug_logs: bool = True

    prefered_llm_api: Client = get_deepseek_client()
    prefered_languages_descriptions: list[str] = ["EN", "NL", "FR"]

    class Config:
        env_file = "../.env", "../.env.prod"
        env_file_encoding = "utf-8"
