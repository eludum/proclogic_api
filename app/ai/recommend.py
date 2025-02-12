from openai import OpenAI

from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.crud.mapper import get_descr_as_str
from app.schemas.publication_schemas import CompanySchema, PublicationSchema

settings = Settings()


# TODO: add recommendation engine using llm: https://cookbook.openai.com/examples/recommendation_using_embeddings
def get_recommendation(
    publication: PublicationSchema, company: CompanySchema, client: OpenAI = None
) -> str:

    # TODO: implement PublicationOut schema
    client = get_openai_client() if not client else client

    interested_cpv_codes_str = ", ".join(
        cpv_code.code for cpv_code in company.interested_cpv_codes
    )

    dossier_title_str = get_descr_as_str(publication.dossier.titles)

    dossier_desc_str = get_descr_as_str(publication.dossier.descriptions)

    lot_title_str = ""
    lot_desc_str = ""
    for i, lot in enumerate(publication.lots):
        if i < len(publication.lots) - 1:
            lot_title_str += (
                str(i + 1)
                + ". lot title: "
                + get_descr_as_str(lot.titles)
                + ", "
                + "\n"
            )

            lot_desc_str += (
                str(i + 1)
                + ". lot description: "
                + get_descr_as_str(lot.descriptions)
                + ", "
                + "\n"
            )
        else:
            lot_title_str += (
                str(i + 1) + ". lot title: " + get_descr_as_str(lot.titles) + "\n"
            )

            lot_desc_str += (
                str(i + 1)
                + ". lot description: "
                + get_descr_as_str(lot.descriptions)
                + "\n"
            )

    additional_cpv_codes_str = ", ".join(
        cpv_code.code for cpv_code in publication.cpvAdditionalCodes
    )

    completion = client.chat.completions.create(
        model="deepseek-chat",  # TODO: adapt according to AI model used
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
                        "text": f"The company is {company.name}, they do {company.summary_activities}. The company accreditations are {str(company.accreditations) if company.accreditations else 'not found in database'}. The max amount of publication value in EUR they are interested in is {company.max_publication_value if company.max_publication_value else 'not found in database'}. The CPV codes they are interested in is {interested_cpv_codes_str}. The publication main CPV code is {publication.cpvMainCode.code}. The additional CPV codes for the publication are: {additional_cpv_codes_str}. The publication title is {dossier_title_str} and the description is {dossier_desc_str}."
                        + "\n"
                        + f"The different lots within this publication are: "
                        + "\n"
                        + f"{lot_title_str}With their respective descriptions:"
                        + "\n"
                        + f"{lot_desc_str}Is this a good fit for them?",
                    }
                ],
            },
        ],
        # TODO: to be finetuned
        # temperature=1.0,
    )

    return True if completion.choices[0].message.content == "yes" else False
