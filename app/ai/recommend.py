from io import BytesIO
import logging
import json
import xml.etree.ElementTree as ET
from typing import Dict, Any

from openai import OpenAI
from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_schemas import PublicationSchema
from app.util.publication_utils.publication_converter import PublicationConverter

settings = Settings()


def handle_json_response_formats(response_text: str) -> dict:
    if "```json" in response_text:
        json_start = response_text.find("```json\n") + len("```json\n")
        json_end = response_text.rfind("\n```")
        return json.loads(response_text[json_start:json_end])
    else:
        # If not in code block format, try to parse the entire text
        return json.loads(response_text)


def extract_data_from_xml(xml_content: str) -> Dict[str, Any]:
    """
    Extract key information from XML using Python's ElementTree before using AI.
    Returns a dictionary with extracted data or an empty dict if parsing fails.
    """
    try:
        # Parse XML content
        root = ET.fromstring(xml_content)

        # Define namespaces (adjust based on your actual XML)
        namespaces = {
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
            "efbc": "http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1",
        }

        # Extract award information
        result = {}

        # Extract winner information
        try:
            # Look for winner organization in NoticeResult/LotTender/TenderingParty
            winner_paths = [
                ".//efac:NoticeResult/efac:LotTender/efac:TenderingParty/efac:Tenderer",
                ".//efac:NoticeResult/efac:TenderingParty/efac:Tenderer",
            ]

            for path in winner_paths:
                winner_elements = root.findall(path, namespaces)
                if winner_elements:
                    # Get organization ID reference
                    org_id = winner_elements[0].find("cbc:ID", namespaces).text

                    # Find organization with this ID
                    org_element = root.find(
                        f'.//efac:Organization/efac:Company/cac:PartyIdentification/cbc:ID[.="{org_id}"]/../..',
                        namespaces,
                    )
                    if org_element:
                        name_element = org_element.find(
                            ".//cac:PartyName/cbc:Name", namespaces
                        )
                        if name_element is not None:
                            result["winner"] = name_element.text
                            break
        except Exception as e:
            logging.warning(f"Error extracting winner: {e}")

        # Extract contract value
        try:
            # Try different paths for total amount
            amount_paths = [
                ".//cbc:TotalAmount",
                ".//cbc:PayableAmount",
                ".//efac:NoticeResult/cbc:TotalAmount",
            ]

            for path in amount_paths:
                amount_element = root.find(path, namespaces)
                if amount_element is not None:
                    result["value"] = float(amount_element.text)
                    break
        except Exception as e:
            logging.warning(f"Error extracting value: {e}")
            result["value"] = 0

        return result
    except Exception as e:
        logging.error(f"Failed to parse XML with ElementTree: {e}")
        return {}


def get_recommendation(
    publication: PublicationSchema,
    company: CompanySchema,
    client: OpenAI = None,
) -> tuple[bool, float]:
    """
    Determine if a publication is a good match for a company.
    Uses PublicationConverter to prepare structured recommendation input.

    Returns:
        Tuple[bool, float]: (is_recommended, match_percentage)
    """
    client = client or get_openai_client()

    # Use the PublicationConverter to create a structured prompt
    structured_prompt = PublicationConverter.to_ai_prompt_format(
        publication_schema=publication, company_schema=company
    )

    # Add assessment criteria to the structured prompt
    prompt = f"""
    TASK: Evaluate the match between this company and publication for procurement.
    
    {structured_prompt}
    
    ASSESSMENT CRITERIA:
    1. Sector alignment: Does the publication's sector match company's interests?
    2. Geographic alignment: Does the publication location match company's regions?
    3. Capability match: Does the company have the capability to fulfill requirements?
    4. Value match: Is the value in line with company's capacity?
    5. Accreditation match: Does the company have required accreditations?
    
    Analyze the match comprehensively across all criteria.
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
                You are a public procurement matching system designed to determine whether a procurement opportunity is a good fit for a specific company.
                
                Analyze all provided information about both the company and the procurement opportunity. Consider:
                1. CPV code matches and sector relevance
                2. Geographic region matches
                3. Required accreditations
                4. Value thresholds
                5. Keyword matches in activities, titles and descriptions
                6. The company's experience and capabilities
                
                Your response must be a valid JSON with these keys:
                - match (boolean): True if a match is found
                - match_percentage (float): Between 0 and 100, indicating confidence level

                Provide an accurate assessment based on all data.

                Translate the data you are given if needed.
                """,
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    try:
        match_result = handle_json_response_formats(
            completion.choices[0].message.content
        )
        match = match_result.get("match", False)
        match_percentage = match_result.get("match_percentage", 0.0)

        match = bool(match)
        match_percentage = float(match_percentage)

        return match, match_percentage
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logging.error(f"Error processing recommendation result: {e}")
        return False, 0.0


def summarize_publication_award(xml: str, client: OpenAI = None) -> dict:
    """
    Extract award information from publication XML.
    First tries to parse with ElementTree, falls back to AI if needed.

    Returns:
        dict: Contains winner (str) and value (int)
    """
    # First try to extract data using Python's XML parser
    extracted_data = extract_data_from_xml(xml)

    if extracted_data and "winner" in extracted_data and "value" in extracted_data:
        logging.info("Successfully extracted award data using XML parser")
        return extracted_data

    # Fall back to using AI if Python parsing was unsuccessful
    logging.info("Falling back to AI for award data extraction")
    client = client or get_openai_client()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                # TODO: do something extra with additional info
                "role": "system",
                "content": """
                    You are a public procurement assistant tasked with summarizing the award of a publication.
                    Extract the winner (contractor name) and the contract value from the XML.
                    If multiple winners or values exist, choose the primary one.
                    Respond in JSON with these keys:
                    - winner (string): The name of the winning contractor
                    - value (integer): The contract value in euros as an integer (no decimal places)
                    - date (string, optional): The award date if available in YYYY-MM-DD format
                    - contract_ref (string, optional): The contract reference number if available
                """,
            },
            {
                "role": "user",
                "content": f"Extract the winner name and contract value from this XML: {xml}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # Lower temperature for more factual extraction
    )

    try:
        result = handle_json_response_formats(completion.choices[0].message.content)
        # Ensure we have both required fields with proper types
        if "winner" not in result:
            result["winner"] = "Unknown"
        if "value" not in result or not isinstance(result["value"], (int, float)):
            result["value"] = 0
        return result
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Error extracting award data via AI: {e}")
        return {"winner": "Unknown", "value": 0}


def summarize_publication_without_files(
    publication: PublicationSchema, xml: str, client: OpenAI = None
) -> str:
    """
    Generate a summary of the publication without considering attached files.
    Uses PublicationConverter to create structured input.

    Returns:
        str: Dutch summary of the publication
    """
    client = client or get_openai_client()

    # Use the PublicationConverter to create a structured prompt
    structured_prompt = PublicationConverter.to_ai_prompt_format(
        publication_schema=publication
    )

    # Create a prompt for summarization
    prompt = f"""
    Create a summary in Dutch of this procurement:
    
    {structured_prompt}

    Additional XML information: {xml}
    
    Create a concise but complete summary that describes the most important aspects of this procurement.
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a public procurement assistant specialized in summarizing government tenders.
                Your task is to create clear, concise summaries that help businesses quickly understand if a tender is relevant to them.
                
                IMPORTANT: Always respond in fluent, professional Dutch regardless of the language of the input.
                
                Structure your summary as follows:
                1. Start with a brief introduction of the project (1-2 sentences)
                2. Describe the purpose and key requirements
                3. Mention important deadlines, required accreditations or qualifications
                4. Include relevant budget information if available
                5. End with practical information about submission process (also redirect them to publicprocurement.be/publication-workspaces/publication_workspace_id/general, replace publication_workspace_id with the actual publication_workspace_id) in the prompt)
                
                Use a professional, informative tone. Focus on concrete, actionable information.
                Highlight what a potential bidder needs to know to decide if this tender is worth pursuing.

                Translate the data you are given if needed.
                """,
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    return completion.choices[0].message.content


def summarize_publication_with_files(
    publication: PublicationSchema, xml: str, filesmap: dict, client: OpenAI = None
) -> tuple[str, str, str]:
    client = client or get_openai_client()
    
    structured_prompt = PublicationConverter.to_ai_prompt_format(
            publication_schema=publication
        )

    # Create a prompt for summarization
    prompt = f"""
    Create a summary in Dutch of this procurement:
    
    {structured_prompt}

    Additional XML information: {xml}
    
    Create a concise but complete summary that describes the most important aspects of this procurement.
    """
    try:
        if filesmap:
            # Filter files with the right extensions - ensure consistent lowercase for extension comparison
            filtered_filesmap = {}
            for file_name, file_data in filesmap.items():
                # Get extension in lowercase for comparison
                if "." in file_name:
                    extension = file_name.split(".")[-1].lower()
                    if extension in [ext.lstrip(".") for ext in settings.openai_vector_store_accepted_formats]:
                        filtered_filesmap[file_name] = file_data

            # Make sure we're passing file objects, not dictionaries
            file_objects = []
            for file_name, file_data in filtered_filesmap.items():
                try:
                    # If it's already an IO object, use it directly
                    if hasattr(file_data, "read") and hasattr(file_data, "seek"):
                        file_data.seek(0)  # Reset file position
                        # Ensure the file object has a name attribute with lowercase extension
                        if hasattr(file_data, "name"):
                            original_name = file_data.name
                            if "." in original_name:
                                name_parts = original_name.rsplit(".", 1)
                                file_data.name = f"{name_parts[0]}.{name_parts[1].lower()}"
                        else:
                            # If no name, use the filename with lowercase extension
                            if "." in file_name:
                                name_parts = file_name.rsplit(".", 1)
                                file_data.name = f"{name_parts[0]}.{name_parts[1].lower()}"
                            else:
                                file_data.name = file_name
                        file_objects.append(file_data)
                    # If it's a dictionary with 'content', create a new BytesIO object
                    elif isinstance(file_data, dict) and "content" in file_data:
                        content = file_data["content"]
                        if isinstance(content, bytes):
                            file_obj = BytesIO(content)
                            # Set name with lowercase extension
                            if "name" in file_data:
                                original_name = file_data["name"]
                                if "." in original_name:
                                    name_parts = original_name.rsplit(".", 1)
                                    file_obj.name = f"{name_parts[0]}.{name_parts[1].lower()}"
                                else:
                                    file_obj.name = original_name
                            else:
                                # Use filename with lowercase extension
                                if "." in file_name:
                                    name_parts = file_name.rsplit(".", 1)
                                    file_obj.name = f"{name_parts[0]}.{name_parts[1].lower()}"
                                else:
                                    file_obj.name = file_name
                            file_objects.append(file_obj)
                except Exception as file_error:
                    logging.error(f"Error processing file {file_name}: {file_error}")
                    continue

            if file_objects:
                vector_store = client.vector_stores.create(
                    name=f"publication_workspace_{publication.publication_workspace_id}"
                )

                file_batch = client.vector_stores.file_batches.upload_and_poll(
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
                    "content": f"Summarize the publication and attached documents. {prompt} XML: {xml}",
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

        message_content = handle_json_response_formats(messages[0].content[0].text.value)

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