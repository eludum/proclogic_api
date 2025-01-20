from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_token_url: str
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

    class Config:
        env_file = "../.env", "../.env.prod"
        env_file_encoding = "utf-8"
