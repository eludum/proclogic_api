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
) -> dict:
    client = client or get_openai_client()

    publication_info = PublicationInfo()
    publication_info.convert_publication_to_str(publication)
    

    interested_sectors_as_cpv_str = ", ".join(
        f"{sector.sector}: {sector.cpv_codes}" for sector in company.interested_sectors
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement ranking system designed to determine whether a procurement opportunity is a good fit for a specific company. Your response must be a JSON with keys: match (True/False) and match_percentage.",
            },
            {
                "role": "user",
                "content": (
                    f"The company {company.name} specializes in {company.summary_activities}. "
                    f"Accreditations: {get_accreditations_as_str(company.accreditations) if company.accreditations else 'not found in database'}. "
                    f"Max publication value: {company.max_publication_value if company.max_publication_value else 'not found in database'}. "
                    f"Interested CPV codes: {interested_sectors_as_cpv_str}. "
                    f"Publication CPV codes: Main {publication.cpv_main_code.code}, Additional {publication_info.additional_cpv_codes_str}. "
                    f"Title: {publication_info.dossier_title_str}. "
                    f"Description: {publication_info.dossier_desc_str}. "
                    f"Lots: {publication_info.lot_str}. "
                    "Is this a good fit for them?"
                ),
            },
        ],
    )
    return json.loads(completion.choices[0].message.content)


def summarize_publication_award(xml: str, client: OpenAI = None) -> dict:
    client = client or get_openai_client()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement assistant tasked with summarizing the award of a publication. Respond in JSON with keys: winner and value.",
            },
            {
                "role": "user",
                "content": f"The XML of the publication is: {xml}",
            },
        ],
    )
    return json.loads(completion.choices[0].message.content)


def summarize_publication_without_files(
    publication: PublicationSchema, xml: str, client: OpenAI = None
) -> str:
    client = client or get_openai_client()
    publication_info = PublicationInfo()
    publication_info.convert_publication_to_str(publication)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement assistant summarizing a publication. Respond in Dutch with a concise summary in fluent text.",
            },
            {
                "role": "user",
                "content": (
                    f"Summarize the publication: "
                    f"Main CPV code: {publication.cpv_main_code.code}. "
                    f"Additional CPV codes: {publication_info.additional_cpv_codes_str}. "
                    f"Title: {publication_info.dossier_title_str}. "
                    f"Description: {publication_info.dossier_desc_str}. "
                    f"Lots: {publication_info.lot_str}. "
                    f"XML: {xml}"
                ),
            },
        ],
    )
    return completion.choices[0].message.content


def summarize_publication_with_files(
    publication: PublicationSchema, xml: str, filesmap: dict, client: OpenAI = None
) -> tuple[str, str, str]:
    client = client or get_openai_client()

    publication_info = PublicationInfo()
    publication_info.convert_publication_to_str(publication)

    try:
        vector_store = client.beta.vector_stores.create(
            name=f"publication_workspace_{publication.publication_workspace_id}"
        )

        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=list(filesmap.values()),
        )

        if file_batch.status != "completed":
            logging.error("File upload failed.")
            return None, None, None

        assistant = client.beta.assistants.update(
            assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
        )

        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": f"Summarize the publication and attached documents. CPV codes: {publication.cpv_main_code.code}, {publication_info.additional_cpv_codes_str}. Title: {publication_info.dossier_title_str}. Description: {publication_info.dossier_desc_str}. Lots: {publication_info.lot_str}. XML: {xml}",
                }
            ]
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id
        )
        messages = list(
            client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id)
        )

        if not messages:
            logging.error("No response from assistant.")
            return None, None, None

        message_content = json.loads(messages[0].content[0].text)
        summary = message_content.get("summary", "No summary available.")
        estimated_value = message_content.get(
            "estimated_value", "No estimated value available."
        )
        citations = [
            f"[{i}] {client.files.retrieve(ann['file_citation']['file_id']).filename}"
            for i, ann in enumerate(message_content.get("annotations", []))
            if "file_citation" in ann
        ]

        return estimated_value, summary, "\n".join(citations)
    except Exception as e:
        logging.error(f"Failed to summarize files: {e}")
        return None, None, None
