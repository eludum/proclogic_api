from app.config.settings import Settings
from openai import OpenAI

settings = Settings()


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)
