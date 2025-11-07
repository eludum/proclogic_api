from app.config.settings import settings
from openai import OpenAI




def get_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)
