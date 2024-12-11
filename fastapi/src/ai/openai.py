from openai import AsyncOpenAI

from config.config import get_settings
from schemas.company import Company
from schemas.ted_schemas import Notice

settings = get_settings()


async def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def get_openai_answer(notice: Notice, company: Company) -> str:
    # TODO:
    # https://norahsakal.com/blog/chatgpt-product-recommendation-embeddings/
    # https://norahsakal.com/blog/naive-rag-dead-long-live-agents/
    client = await get_openai_client()
    completion = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": 'You are a public procurement ranking system designed to determine whether a procurement opportunity is a good fit for a specific company. Your response to any given procurement must be either "yes" or "no".',
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        # TODO: make profile per company
                        "type": "text",
                        "text": f"The company is {company.name}, they do {company.summary_activities}. The notice title is {notice.notice_title}. Is this a good fit for them?",
                    }
                ],
            },
        ],
        # TODO: to be fine tuned
        temperature=0.0,
    )

    return completion.choices[0].message.content
