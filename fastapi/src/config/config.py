from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    TED_API_KEY: str
    redis_host: str = 'localhost'
    postgres_host: str = 'localhost'
    TEMPLATE_FOLDER: str = 'email_template'

    class Config:
        env_file = ".env"


async def get_settings() -> Settings:
    return Settings()
