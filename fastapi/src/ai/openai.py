from openai import AsyncOpenAI

from config.settings import Settings
from schemas.publication_schemas import CompanySchema, PublicationSchema

settings = Settings


async def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def get_openai_answer(publication: PublicationSchema, company: CompanySchema) -> str:
    # TODO:
    # https://norahsakal.com/blog/chatgpt-product-recommendation-embeddings/
    # https://norahsakal.com/blog/naive-rag-dead-long-live-agents/
    client = await get_openai_client()
    dossier_str = ""
    for desc in publication.dossier.descriptions:
        dossier_str += f"{desc.text}\n"
    lots_str = ""
    for lot in publication.lots:
         for desc in lot.descriptions:
            if desc.language == "EN":
                lots_str += f"{desc.text}\n"
    completion = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": 'You are a public procurement ranking system designed to determine whether a procurement opportunity (aka publication) is a good fit for a specific company. Beware some info given in the publication is in another language please adapt accordingly. Your response to any given publication must be either "yes" or "no".',
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        # TODO: make profile per company
                        "type": "text",
                        "text": f"The company is {company.name}, they do {company.summary_activities}. The publication title is {dossier_str}. The different lots within this publication are {lots_str}. Is this a good fit for them?",
                    }
                ],
            },
        ],
        # TODO: to be fine tuned
        temperature=0.0,
    )

    return completion.choices[0].message.content
