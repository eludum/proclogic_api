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
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'efac': 'http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1',
            'efbc': 'http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1'
        }
        
        # Extract award information
        result = {}
        
        # Extract winner information
        try:
            # Look for winner organization in NoticeResult/LotTender/TenderingParty
            winner_paths = [
                './/efac:NoticeResult/efac:LotTender/efac:TenderingParty/efac:Tenderer',
                './/efac:NoticeResult/efac:TenderingParty/efac:Tenderer'
            ]
            
            for path in winner_paths:
                winner_elements = root.findall(path, namespaces)
                if winner_elements:
                    # Get organization ID reference
                    org_id = winner_elements[0].find('cbc:ID', namespaces).text
                    
                    # Find organization with this ID
                    org_element = root.find(f'.//efac:Organization/efac:Company/cac:PartyIdentification/cbc:ID[.="{org_id}"]/../..', namespaces)
                    if org_element:
                        name_element = org_element.find('.//cac:PartyName/cbc:Name', namespaces)
                        if name_element is not None:
                            result['winner'] = name_element.text
                            break
        except Exception as e:
            logging.warning(f"Error extracting winner: {e}")
        
        # Extract contract value
        try:
            # Try different paths for total amount
            amount_paths = [
                './/cbc:TotalAmount',
                './/cbc:PayableAmount',
                './/efac:NoticeResult/cbc:TotalAmount'
            ]
            
            for path in amount_paths:
                amount_element = root.find(path, namespaces)
                if amount_element is not None:
                    result['value'] = float(amount_element.text)
                    break
        except Exception as e:
            logging.warning(f"Error extracting value: {e}")
            result['value'] = 0
        
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

    # Use the converter to prepare input for the recommendation
    recommendation_input = PublicationConverter.to_recommendation_input(publication, company)

    # Create a more structured prompt using the converter output
    prompt = f"""
    TASK: Evaluate the match between this company and publication for procurement.
    
    COMPANY PROFILE:
    - Name: {company.name}
    - Summary activities: {company.summary_activities}
    - Interested sectors: {', '.join(f"{sector.sector}" for sector in company.interested_sectors)}
    - Accreditations: {company.accreditations if company.accreditations else 'None'}
    - Regions: {', '.join(company.operating_regions) if company.operating_regions else 'Not specified'}
    
    PUBLICATION DETAILS:
    - Title: {PublicationConverter.get_descr_as_str(publication.dossier.titles)}
    - CPV code: {publication.cpv_main_code.code}
    - Additional CPV codes: {', '.join(cpv.code for cpv in publication.cpv_additional_codes)}
    - Description: {PublicationConverter.get_descr_as_str(publication.dossier.descriptions)}
    
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
                "content": "You are a procurement matching system that evaluates whether a business opportunity matches a company's capabilities and interests. Respond with JSON containing match (boolean) and match_percentage (float 0-100)."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={"type": "json_object"},
    )
    
    try:
        match_result = json.loads(completion.choices[0].message.content)
        match = match_result.get("match", False)
        match_percentage = match_result.get("match_percentage", 0.0)
        
        # Ensure match is boolean and percentage is float between 0-100
        match = bool(match)
        match_percentage = min(max(float(match_percentage), 0.0), 100.0)
        
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
    
    if extracted_data and 'winner' in extracted_data and 'value' in extracted_data:
        logging.info("Successfully extracted award data using XML parser")
        return extracted_data
    
    # Fall back to using AI if Python parsing was unsuccessful
    logging.info("Falling back to AI for award data extraction")
    client = client or get_openai_client()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a public procurement assistant tasked with extracting award information from XML. Respond with JSON containing winner (string) and value (numeric)."
            },
            {
                "role": "user",
                "content": f"Extract the winner name and contract value from this XML: {xml}"
            }
        ],
        response_format={"type": "json_object"},
    )
    
    try:
        result = json.loads(completion.choices[0].message.content)
        # Ensure we have both required fields with proper types
        if 'winner' not in result:
            result['winner'] = 'Unknown'
        if 'value' not in result or not isinstance(result['value'], (int, float)):
            result['value'] = 0
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
    
    # Use the converter to create structured summary input
    publication_data = PublicationConverter.to_output_schema(publication)
    
    # Create a more structured prompt
    prompt = f"""
    Create a summary in Dutch of this procurement:
    
    TITLE: {publication_data.title}
    PUBLICATION ID: {publication_data.workspace_id}
    PUBLICATION DATE: {publication_data.publication_date}
    DEADLINE: {publication_data.submission_deadline}
    ORGANIZATION: {publication_data.organisation}
    CPV CODE: {publication_data.cpv_code} ({publication_data.sector})
    DESCRIPTION: {publication_data.original_description}
    
    Create a concise but complete summary that describes the most important aspects of this procurement.
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are an assistant that summarizes procurements in clear and professional Dutch."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
    )
    
    return completion.choices[0].message.content


def summarize_publication_with_files(
    publication: PublicationSchema, xml: str, filesmap: dict, client: OpenAI = None
) -> tuple[float, str, str]:
    """
    Generate a summary of the publication including content from attached files.
    Uses a vector store approach for large file analysis.
    
    Returns:
        tuple: (estimated_value, summary, citations)
    """
    client = client or get_openai_client()
    
    # Use the converter to create structured publication data
    publication_data = PublicationConverter.to_output_schema(publication)
    
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

            # Prepare file objects for vector store
            file_objects = []
            for file_name, file_data in filtered_filesmap.items():
                # Handle different types of file objects
                if hasattr(file_data, "read") and hasattr(file_data, "seek"):
                    file_data.seek(0)  # Reset file position
                    file_objects.append(file_data)
                elif isinstance(file_data, dict) and "content" in file_data:
                    content = file_data["content"]
                    if isinstance(content, bytes):
                        file_obj = BytesIO(content)
                        file_obj.name = file_data.get("name", file_name)
                        file_objects.append(file_obj)

            # Create vector store and upload files
            vector_store = None
            if file_objects:
                # Create vector store for this publication
                vector_store = client.beta.vector_stores.create(
                    name=f"pub_{publication.publication_workspace_id}"
                )
                
                logging.info(f"Uploading {len(file_objects)} files to vector store {vector_store.id}")
                
                # Upload files to vector store
                file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store.id,
                    files=file_objects
                )
                
                if file_batch.status != "completed":
                    logging.error(f"File upload failed: {file_batch.status}")
                    return 0, "Error processing documents.", ""
            
            # Create assistant with vector store access if available
            assistant = client.beta.assistants.create(
                name=f"Publication Summarizer {publication.publication_workspace_id}",
                model="gpt-4o-mini",
                tools=[{"type": "file_search"}],
                tool_resources={
                    "file_search": {"vector_store_ids": [vector_store.id] if vector_store else []}
                },
                instructions=f"""
                You are a specialist in analyzing procurement documents.
                Analyze the procurement and associated documents to create a comprehensive summary.
                Also identify the estimated value of the procurement in EUR.
                
                Provide your output as JSON with the following fields:
                - summary: A comprehensive summary in Dutch of the procurement
                - estimated_value: The estimated value of the procurement in EUR as an integer (without decimals)
                """
            )

            # Create thread and add instructions
            prompt = f"""
            Analyze this procurement and the attached documents:
            
            TITLE: {publication_data.title}
            PUBLICATION ID: {publication_data.workspace_id}
            PUBLICATION DATE: {publication_data.publication_date}
            DEADLINE: {publication_data.submission_deadline}
            ORGANIZATION: {publication_data.organisation}
            CPV CODE: {publication_data.cpv_code} ({publication_data.sector})
            DESCRIPTION: {publication_data.original_description}
            
            Create a comprehensive summary that describes the key aspects including information from the documents.
            Also determine the estimated value of the procurement (in EUR).
            """

            thread = client.beta.threads.create(
                messages=[{"role": "user", "content": prompt}]
            )

            # Run the assistant
            run = client.beta.threads.runs.create_and_poll(
                thread_id=thread.id, assistant_id=assistant.id
            )
            
            # Process response
            if run.status == "completed":
                messages = list(client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1))
                if messages:
                    message_content = messages[0].content[0].text
                    response_text = message_content.value
                    
                    # Extract JSON content if present
                    if "```json" in response_text:
                        json_start = response_text.find("```json\n") + len("```json\n")
                        json_end = response_text.rfind("\n```")
                        json_content = response_text[json_start:json_end]
                    else:
                        # If not in code block format, try to parse the entire text
                        json_content = response_text
                    
                    try:
                        result = json.loads(json_content)
                        summary = result.get("summary", "No summary available.")
                        estimated_value = int(float(result.get("estimated_value", 0)))
                        
                        # Collect citations
                        citations = []
                        for i, annotation in enumerate(message_content.annotations):
                            if hasattr(annotation, 'file_citation'):
                                file_id = annotation.file_citation.file_id
                                filename = client.files.retrieve(file_id).filename
                                citations.append(f"[{i}] {filename}")
                        
                        return estimated_value, summary, "\n".join(citations)
                    except (json.JSONDecodeError, ValueError) as e:
                        logging.error(f"Error parsing assistant response: {e}")
            
            # Clean up 
            if vector_store:
                try:
                    client.beta.assistants.delete(assistant_id=assistant.id)
                    client.beta.vector_stores.delete(vector_store_id=vector_store.id)
                except Exception as e:
                    logging.warning(f"Error cleaning up resources: {e}")
        
        # Fallback for when filesmap is empty or processing fails
        summary = summarize_publication_without_files(publication, xml, client)
        return 0, summary, ""
        
    except Exception as e:
        logging.error(f"Failed to summarize files: {e}")
        return 0, "An error occurred while analyzing this procurement.", ""