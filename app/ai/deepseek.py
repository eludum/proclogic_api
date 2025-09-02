from app.config.settings import settings
from openai import OpenAI




def get_deepseek_client() -> OpenAI:
    return OpenAI(
        api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com"
    )
