import logging
import json

from openai import OpenAI
from app.util.converter import PublicationInfo
from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_schemas import PublicationSchema
from app.util.converter import get_accreditations_as_str

settings = Settings()


def get_recommendation(
    publication: PublicationSchema,
    company: CompanySchema,
    client: OpenAI = None,
) -> str:

    client = get_openai_client() if not client else client

    publication_info = PublicationInfo()
    publication_info.convert_publication_to_str(publication)

    interested_sectors_as_cpv_str = ""
    for sector in company.interested_sectors:
        interested_sectors_as_cpv_str += f"{sector.sector}: " + str(sector.cpv_codes)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # TODO: adapt according to AI model used
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
                        # TODO: more info about why it is a match
                        # keyword search documents
                        "type": "text",
                        "text": f"The company is {company.name}, they do {company.summary_activities}. The company accreditations are {get_accreditations_as_str(company.accreditations) if company.accreditations else 'not found in database'}. The max amount of publication value in EUR they are interested in is {company.max_publication_value if company.max_publication_value else 'not found in database'}. The CPV codes the company is interested in are {interested_sectors_as_cpv_str}. The publication main CPV code is {publication.cpv_main_code.code}. The additional CPV codes for the publication are: {publication_info.additional_cpv_codes_str}. The publication title is {publication_info.dossier_title_str} and the description is {publication_info.dossier_desc_str}."
                        + "\n"
                        + f"The different lots within this publication are: "
                        + "\n"
                        + f"{publication_info.lot_title_str}With their respective descriptions:"
                        + "\n"
                        + f"{publication_info.lot_desc_str}"
                        + "\n"
                        + "Is this a good fit for them?",
                    }
                ],
            },
        ],
        # TODO: to be finetuned
        # temperature=1.0,
    )

    return True if completion.choices[0].message.content.lower() == "yes" else False


def summarize_publication_award(
    xml: str, client: OpenAI = None
) -> str:
    client = get_openai_client() if not client else client
    
    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # TODO: adapt according to AI model used
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You are a public procurement ranking system designed to determine whether a procurement opportunity (aka publication) is a good fit for a specific company. In this context, you are asked to summarize the award for a publication. Respond in a json format with the following keys: winner, value and currency. Keep it concise.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"The xml of the publication is: {xml}",
                    }
                ],
            },
        ],
        # TODO: to be finetuned
        # temperature=1.0,
    )

    return json.loads(completion.choices[0].message.content)


def summarize_publication_without_files(
    publication: PublicationSchema, xml: str, client: OpenAI = None
) -> str:
    client = get_openai_client() if not client else client
    publication_info = PublicationInfo()
    publication_info.convert_publication_to_str(publication)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # TODO: adapt according to AI model used
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You are a public procurement ranking system designed to determine whether a procurement opportunity (aka publication) is a good fit for a specific company. In this context, you are asked to summarize a publication. Your response must be a summary with all relevant info. Reply in a couple of paragraphs of fluent text. Keep it concise. Reply in Dutch.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"The publication main CPV code is {publication.cpv_main_code.code}. The additional CPV codes for the publication are: {publication_info.additional_cpv_codes_str}. The publication title is {publication_info.dossier_title_str} and the description is {publication_info.dossier_desc_str}."
                        + "\n"
                        + f"The different lots within this publication are: "
                        + "\n"
                        + f"{publication_info.lot_title_str}With their respective descriptions:"
                        + "\n"
                        + f"{publication_info.lot_desc_str}"
                        + "\n"
                        + f"The xml of the publication is: {xml}",
                    }
                ],
            },
        ],
        # TODO: to be finetuned
        # temperature=1.0,
    )

    return completion.choices[0].message.content


def summarize_publication_with_files(
    publication: PublicationSchema, xml: str, filesmap: dict, client: OpenAI = None
) -> str:
    client = get_openai_client() if not client else client

    publication_info = PublicationInfo()
    publication_info.convert_publication_to_str(publication)

    try:
        vector_store = client.beta.vector_stores.create(
            name=f"publication_workspace_{publication.publication_workspace_id}"
        )

        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=[file_data for file_data in filesmap.values()],
        )

        while file_batch.status != "completed":
            if file_batch.status == "failed":
                logging.error(f"Failed to upload files to vector store: {file_batch}")
                return None
            if file_batch.status == "in_progress":
                continue

        assistant = client.beta.assistants.update(
            assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
        )

        # Create a thread and attach the file to the message
        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Can you summarize the publication and the documents attached. The publication main CPV code is {publication.cpv_main_code.code}. The additional CPV codes for the publication are: {publication_info.additional_cpv_codes_str}. The publication title is {publication_info.dossier_title_str} and the description is {publication_info.dossier_desc_str}."
                            + "\n"
                            + f"The different lots within this publication are: "
                            + "\n"
                            + f"{publication_info.lot_title_str}With their respective descriptions:"
                            + "\n"
                            + f"{publication_info.lot_desc_str}"
                            + "\n"
                            + f"The xml of the publication is: {xml}",
                        }
                    ],
                    # Attach the new file to the message.
                    # "attachments": [
                    #     { "file_id": message_file.id, "tools": [{"type": "file_search"}] }
                    # ],
                }
            ]
        )

        # Use the create and poll SDK helper to create a run and poll the status of
        # the run until it's in a terminal state.

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id
        )

        messages = list(
            client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id)
        )

        message_content = messages[0].content[0].text
        annotations = message_content.annotations
        citations = []
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f"[{index}]"
            )
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        return message_content.value, "\n".join(citations)

    except Exception as e:
        logging.error(f"Failed to summarize files: {e}")
        return None

    # finally:
    #     assistant = client.beta.assistants.update(
    #         assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
    #         tool_resources={"file_search": {"vector_store_ids": []}},
    #     )

    #     client.beta.vector_stores.delete(vector_store_id=vector_store.id)
    #     files = client.files.list()

    #     for file in files:
    #         client.files.delete(file.id)
    #     client.files.list()
