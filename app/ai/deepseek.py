from app.config.settings import Settings
from openai import OpenAI

settings = Settings()


def get_deepseek_client() -> OpenAI:
    return OpenAI(
        api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com"
    )
