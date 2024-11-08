from openai import AsyncOpenAI

from schemas.pubproc_schemas import Publication
from config.config import get_settings

settings = get_settings()


async def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def get_openai_answer(publication: Publication) -> str:
    client = get_openai_client()
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You are a public procurement ranking system that answers whether a procurement is the right fit for a given company. You have to answer with only yes or no to any given procurement. Also state how sure you are that the procurement is the right fit, do this in percentages."
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        # TODO: make profile per company
                        "type": "text",
                        "text": f"The company is EBM, they do repair and maintanence of buildings. {publication.dossier} Is this a good fit for them?"
                    }
                ]
            }
        ]
        # TODO: to be fine tuned
        # temperature=0.2,
        # top_p=0.2
    )

    return completion.choices[0].message.content
