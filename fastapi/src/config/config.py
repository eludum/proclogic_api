from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    pubproc_client_id: str
    pubproc_client_secret: str
    pubproc_token_url: str = 'https://public.pr.fedservices.be/api/oauth2/token'
    pubproc_token: str
    pubproc_token_exp: str
    redis_host: str = 'localhost'
    postgres_host: str = 'localhost'
    postgres_con_url: str = 'postgresql+asyncpg://postgres:postgres@localhost:5432/postgres'
    TEMPLATE_FOLDER: str = 'email_template'

    class Config:
        env_file = ".env"


async def get_settings() -> Settings:
    return Settings()
