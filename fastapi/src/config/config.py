from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    redis_host: str = 'localhost'
    postgres_host: str = 'localhost'
