from openai import OpenAI

from ai.deepseek import get_deepseek_client
from config.settings import Settings
from schemas.publication_schemas import CompanySchema, PublicationSchema

settings = Settings()


# TODO: add recommendation engine using llm
def get_answer(
    publication: PublicationSchema, company: CompanySchema, client: OpenAI = None
) -> str:

    client = get_deepseek_client() if client is None else client

    dossier_title_str = ""
    dossier_desc_str = ""
    lot_title_str = ""
    lot_desc_str = ""
    additional_cpv_codes_str = ""

    for dossier_title in publication.dossier.titles:
        if dossier_title.language == "EN":
            dossier_title_str += f"{dossier_title.text}\n"

    for lot in publication.lots:
        for lot_title in lot.titles:
            if lot_title.language == "EN":
                lot_title_str += f"{lot_title.text}\n"

    for dossier_desc in publication.dossier.descriptions:
        if dossier_desc.language == "EN":
            dossier_desc_str += f"{dossier_desc.text}\n"

    for lot in publication.lots:
        for lot_desc in lot.descriptions:
            if lot_desc.language == "EN":
                lot_desc_str += f"{lot_desc_str.text}\n"

    for cpv_code in publication.cpvAdditionalCodes:
        additional_cpv_codes_str += f"{cpv_code.code}\n"

    completion = client.chat.completions.create(
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
                        "type": "text",
                        "text": f"The company is {company.name}, they do {company.summary_activities}. The company accreditations are {str(company.accreditations)}. The max amount of publication value in EUR they are interested in is {company.max_publication_value}. The CPV codes they are interested in is {company.interested_cpv_codes}. The publication main CPV code is {publication.cpvMainCode.code}. The additional CPV codes for the publication are: {additional_cpv_codes_str}. The publication title is {dossier_title_str} and the description is {dossier_desc_str}. The different lots within this publication are {lot_title_str} with their respective descriptions: {lot_desc_str}. Is this a good fit for them?",
                    }
                ],
            },
        ],
        # TODO: to be fine tuned
        temperature=1.0,
    )

    return completion.choices[0].message.content
