from io import BytesIO
import logging
import json

from openai import OpenAI
from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_schemas import PublicationSchema
from app.util.publication_utils.publication_converter import PublicationConverter

settings = Settings()


def get_recommendation(
    publication: PublicationSchema,
    company: CompanySchema,
    client: OpenAI = None,
) -> tuple[bool, float]:
    client = client or get_openai_client()

    # Use the converter to prepare input for the recommendation
    recommendation_input = PublicationConverter.to_recommendation_input(publication, company)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement ranking system designed to determine whether a procurement opportunity is a good fit for a specific company. Your response must be a JSON with keys: match (True/False, True if match_percentage is greater than 75%) and match_percentage (float between 0 and 100).",
            },
            {
                "role": "user",
                "content": recommendation_input,
            },
        ],
        response_format={"type": "json_object"},
    )
    match_result = json.loads(completion.choices[0].message.content)
    match = match_result["match"]
    match_percentage = match_result["match_percentage"]
    return match, match_percentage


def summarize_publication_award(xml: str, client: OpenAI = None) -> dict:
    client = client or get_openai_client()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement assistant tasked with summarizing the award of a publication. Respond in JSON with keys: winner (str) and value (int).",
            },
            {
                "role": "user",
                "content": f"The XML of the publication is: {xml}",
            },
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(completion.choices[0].message.content)


def summarize_publication_without_files(
    publication: PublicationSchema, xml: str, client: OpenAI = None
) -> str:
    client = client or get_openai_client()
    
    # Use the converter to create a summary input for XML processing
    summary_input = PublicationConverter.to_xml_summary_input(publication)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement assistant summarizing a publication. Respond in Dutch with a concise summary in fluent text.",
            },
            {
                "role": "user",
                "content": f"Summarize the publication: {summary_input} XML: {xml}",
            },
        ],
    )
    return completion.choices[0].message.content


def summarize_publication_with_files(
    publication: PublicationSchema, xml: str, filesmap: dict, client: OpenAI = None
) -> tuple[str, str, str]:
    client = client or get_openai_client()
    
    # Use the converter to create a summary input for XML processing
    summary_input = PublicationConverter.to_xml_summary_input(publication)

    try:
        if filesmap:
            # Filter files with the right extensions
            filtered_filesmap = {
                file_name: file_data
                for file_name, file_data in filesmap.items()
                if file_name.lower().endswith(
                    tuple(settings.openai_vector_store_accepted_formats)
                )
            }

            # Make sure we're passing file objects, not dictionaries
            file_objects = []
            for file_name, file_data in filtered_filesmap.items():
                # If it's already an IO object, use it directly
                if hasattr(file_data, "read") and hasattr(file_data, "seek"):
                    file_data.seek(0)  # Reset file position
                    file_objects.append(file_data)
                # If it's a dictionary with 'content', create a new BytesIO object
                elif isinstance(file_data, dict) and "content" in file_data:
                    content = file_data["content"]
                    if isinstance(content, bytes):
                        file_obj = BytesIO(content)
                        file_obj.name = file_data.get("name", file_name)
                        file_objects.append(file_obj)

            if file_objects:
                vector_store = client.beta.vector_stores.create(
                    name=f"publication_workspace_{publication.publication_workspace_id}"
                )

                file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store.id,
                    files=file_objects,  # Pass the list of file objects
                )

                if file_batch.status != "completed":
                    logging.error("File upload failed.")
                    return None, None, None

                assistant = client.beta.assistants.update(
                    assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
                    tool_resources={
                        "file_search": {"vector_store_ids": [vector_store.id]}
                    },
                    response_format={"type": "json_object"},
                )
            else:
                # No valid files after filtering
                assistant = client.beta.assistants.update(
                    assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
                    tool_resources={"file_search": {"vector_store_ids": []}},
                    response_format={"type": "json_object"},
                )
        else:
            assistant = client.beta.assistants.update(
                assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
                tool_resources={"file_search": {"vector_store_ids": []}},
                response_format={"type": "json_object"},
            )

        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": f"Summarize the publication and attached documents. {summary_input} XML: {xml}",
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

        response_text = messages[0].content[0].text.value
        if "```json" in response_text:
            json_start = response_text.find("```json\n") + len("```json\n")
            json_end = response_text.rfind("\n```")
            json_content = response_text[json_start:json_end]
        else:
            # If not in code block format, try to parse the entire text
            json_content = response_text

        message_content = json.loads(json_content)
        summary = message_content.get("summary", "Geen samenvatting beschikbaar.")
        estimated_value = message_content.get("estimated_value", 0)

        citations = [
            f"[{i}] {client.files.retrieve(ann['file_citation']['file_id']).filename}"
            for i, ann in enumerate(messages[0].content[0].text.annotations)
            if "file_citation" in ann
        ]
        return estimated_value, summary, "\n".join(citations)
    except Exception as e:
        logging.error(f"Failed to summarize files: {e}")
        return None, None, None