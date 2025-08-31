from datetime import datetime
import logging
import json
import xml.etree.ElementTree as ET
from typing import Optional

from openai import OpenAI
from pydantic import ValidationError
from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_schemas import PublicationSchema
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.redis_utils import prepare_files_for_vector_store
from app.schemas.publication_contract_schemas import (
    ContractAddressSchema,
    ContractContactPersonSchema,
    ContractOrganizationSchema,
    ContractSchema,
)

settings = Settings()


def handle_json_response_formats(response_text: str) -> dict:
    """
    Parse a JSON response from the OpenAI API
    """
    if "```json" in response_text:
        json_start = response_text.find("```json\n") + len("```json\n")
        json_end = response_text.rfind("\n```")
        return json.loads(response_text[json_start:json_end])
    else:
        # If not in code block format, try to parse the entire text
        return json.loads(response_text)


def find_text(element, path, namespaces, default=None):
    if element is None:
        return default
    found = element.find(path, namespaces)
    return found.text if found is not None else default


def parse_organization(org_data: dict) -> Optional[ContractOrganizationSchema]:
    if not org_data or not isinstance(org_data, dict):
        return None

    try:
        # Parse address if present
        address = None
        if "address" in org_data and isinstance(org_data["address"], dict):
            address = ContractAddressSchema(**org_data["address"])

        # Parse contact persons if present
        contact_persons = []
        if "contact_persons" in org_data and isinstance(
            org_data["contact_persons"], list
        ):
            for cp_data in org_data["contact_persons"]:
                if isinstance(cp_data, dict):
                    contact_persons.append(ContractContactPersonSchema(**cp_data))

        # Create organization
        org_dict = {
            "name": org_data.get("name", "Unknown"),
            "business_id": org_data.get("business_id"),
            "website": org_data.get("website"),
            "phone": org_data.get("phone"),
            "email": org_data.get("email"),
            "company_size": org_data.get("company_size"),
            "subcontracting": org_data.get("subcontracting"),
            "address": address,
            "contact_persons": contact_persons,
        }

        return ContractOrganizationSchema(**org_dict)
    except Exception as e:
        logging.warning(f"Failed to parse organization: {e}")
        return None


# TODO: make sure all lots are represented in the schames and not only the first one in the gunnning
def extract_data_from_xml(xml_content: str) -> Optional[ContractSchema]:
    """
    Extract contract award information from XML and return a Contract Pydantic model.
    Returns None if parsing fails.
    """

    # Parse XML content
    root = ET.fromstring(xml_content)
    root_tag = root.tag
    if "PriorInformationNotice" in root_tag:
        # TODO: capture different types of notices
        raise ValueError(
            "This is a PriorInformationNotice (planning notice), not an award notice"
        )

    # Define namespaces
    namespaces = {
        "": "urn:oasis:names:specification:ubl:schema:xsd:ContractAwardNotice-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
        "efbc": "http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1",
        "efext": "http://data.europa.eu/p27/eforms-ubl-extensions/1",
        "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    }

    # Helper function to find text safely

    # Extract basic contract information
    notice_id = find_text(root, "cbc:ID", namespaces)
    contract_folder_id = find_text(root, "cbc:ContractFolderID", namespaces)
    internal_id = find_text(root, ".//cac:ProcurementProject/cbc:ID", namespaces)

    # Extract issue date
    issue_date_str = find_text(root, "cbc:IssueDate", namespaces)
    issue_date = None
    if issue_date_str:
        try:
            # Remove timezone info and parse
            date_part = issue_date_str.split("+")[0]
            issue_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        except:
            pass

    # Extract notice type
    notice_type = find_text(root, "cbc:NoticeTypeCode", namespaces)

    # Extract financial information from NoticeResult
    notice_result = root.find(".//efac:NoticeResult", namespaces)
    total_amount = None
    currency = "EUR"
    lowest_amount = None
    highest_amount = None

    if notice_result:
        total_amount_elem = notice_result.find("cbc:TotalAmount", namespaces)
        if total_amount_elem is not None:
            total_amount = float(total_amount_elem.text)
            currency = total_amount_elem.get("currencyID", "EUR")

        # Get amounts from LotResult
        lot_result = notice_result.find(".//efac:LotResult", namespaces)
        if lot_result:
            lower_elem = lot_result.find("cbc:LowerTenderAmount", namespaces)
            higher_elem = lot_result.find("cbc:HigherTenderAmount", namespaces)
            if lower_elem is not None:
                lowest_amount = float(lower_elem.text)
            if higher_elem is not None:
                highest_amount = float(higher_elem.text)

    # Extract publication statistics
    number_publications = None
    number_participation = None

    if notice_result:
        stats = notice_result.findall(
            ".//efac:ReceivedSubmissionsStatistics", namespaces
        )
        for stat in stats:
            code = find_text(stat, "efbc:StatisticsCode", namespaces)
            value = find_text(stat, "efbc:StatisticsNumeric", namespaces)
            if code == "tenders" and value:
                number_publications = int(value)
            elif code == "part-req" and value:
                number_participation = int(value)

    # Extract process information
    auction_elem = root.find(
        ".//cac:AuctionTerms/cbc:AuctionConstraintIndicator", namespaces
    )
    electronic_auction = False
    if auction_elem is not None and auction_elem.text.lower() == "true":
        electronic_auction = True

    # Extract DPS and Framework info
    contracting_systems = root.findall(".//cac:ContractingSystem", namespaces)
    dps = "none"
    framework = "none"
    for system in contracting_systems:
        type_code = find_text(system, "cbc:ContractingSystemTypeCode", namespaces)
        if type_code:
            if "dps" in type_code:
                dps = type_code
            elif "framework" in type_code:
                framework = type_code

    # Extract organizations
    organizations_dict = {}
    orgs_section = root.find(".//efac:Organizations", namespaces)

    if orgs_section:
        for org_elem in orgs_section.findall(".//efac:Organization", namespaces):
            company = org_elem.find("efac:Company", namespaces)
            if company:
                org_id = find_text(
                    company, ".//cac:PartyIdentification/cbc:ID", namespaces
                )

                # Extract organization details
                org_data = {
                    "name": find_text(company, ".//cac:PartyName/cbc:Name", namespaces)
                    or "Unknown",
                    "business_id": find_text(
                        company, ".//cac:PartyLegalEntity/cbc:CompanyID", namespaces
                    ),
                    "website": find_text(company, "cbc:WebsiteURI", namespaces),
                    "phone": find_text(
                        company, ".//cac:Contact/cbc:Telephone", namespaces
                    ),
                    "email": find_text(
                        company, ".//cac:Contact/cbc:ElectronicMail", namespaces
                    ),
                    "company_size": find_text(
                        company, "efbc:CompanySizeCode", namespaces
                    ),
                }

                # Extract address
                address_elem = company.find(".//cac:PostalAddress", namespaces)
                if address_elem:
                    org_data["address"] = ContractAddressSchema(
                        street=find_text(address_elem, "cbc:StreetName", namespaces),
                        city=find_text(address_elem, "cbc:CityName", namespaces),
                        postal_code=find_text(
                            address_elem, "cbc:PostalZone", namespaces
                        ),
                        country=find_text(
                            address_elem,
                            ".//cac:Country/cbc:IdentificationCode",
                            namespaces,
                        ),
                        nuts_code=find_text(
                            address_elem, "cbc:CountrySubentityCode", namespaces
                        ),
                    )

                # Extract contact person
                contact_elem = company.find(".//cac:Contact", namespaces)
                if contact_elem and find_text(contact_elem, "cbc:Name", namespaces):
                    contact = ContractContactPersonSchema(
                        name=find_text(contact_elem, "cbc:Name", namespaces),
                        job_title=find_text(contact_elem, "cbc:JobTitle", namespaces),
                        phone=find_text(contact_elem, "cbc:Telephone", namespaces),
                        email=find_text(contact_elem, "cbc:ElectronicMail", namespaces),
                    )
                    org_data["contact_persons"] = [contact]

                organizations_dict[org_id] = ContractOrganizationSchema(**org_data)

    # Identify organization roles
    contracting_authority = None
    winning_publisher = None
    appeals_body = None
    service_provider = None

    # Get contracting authority
    ca_id = find_text(
        root,
        ".//cac:ContractingParty/cac:Party/cac:PartyIdentification/cbc:ID",
        namespaces,
    )
    if ca_id and ca_id in organizations_dict:
        contracting_authority = organizations_dict[ca_id]

    # Get service provider
    sp_id = find_text(
        root,
        ".//cac:ServiceProviderParty/cac:Party/cac:PartyIdentification/cbc:ID",
        namespaces,
    )
    if sp_id and sp_id in organizations_dict:
        service_provider = organizations_dict[sp_id]

    # Get appeals body
    appeals_id = find_text(
        root,
        ".//cac:AppealReceiverParty/cac:PartyIdentification/cbc:ID",
        namespaces,
    )
    if appeals_id and appeals_id in organizations_dict:
        appeals_body = organizations_dict[appeals_id]

    # Get winning publisher from TenderingParty and add subcontracting info
    if notice_result:
        winner_id = find_text(
            notice_result, ".//efac:TenderingParty/efac:Tenderer/cbc:ID", namespaces
        )
        if winner_id and winner_id in organizations_dict:
            winning_publisher = organizations_dict[winner_id]

            # Extract publication details and add to winning publisher
            lot_tender = notice_result.find(".//efac:LotTender", namespaces)
            if lot_tender:
                subcontracting = find_text(
                    lot_tender,
                    ".//efac:SubcontractingTerm/efbc:TermCode",
                    namespaces,
                )

                # Update the winning publisher with subcontracting info
                winning_publisher.subcontracting = (
                    "Not applicable" if subcontracting == "no" else subcontracting
                )

    # Create the Contract model
    contract = ContractSchema(
        notice_id=notice_id,
        contract_id=contract_folder_id,
        internal_id=internal_id,
        issue_date=issue_date,
        notice_type=notice_type,
        total_contract_amount=total_amount,
        currency=currency,
        lowest_publication_amount=lowest_amount,
        highest_publication_amount=highest_amount,
        number_of_publications_received=number_publications,
        number_of_participation_requests=number_participation,
        electronic_auction_used=electronic_auction,
        dynamic_purchasing_system=dps,
        framework_agreement=framework,
        contracting_authority=contracting_authority,
        winning_publisher=winning_publisher,
        appeals_body=appeals_body,
        service_provider=service_provider,
    )

    return contract


def summarize_publication_contract(
    xml: str, client: OpenAI = None
) -> Optional[ContractSchema]:
    """
    Extract award information from publication XML.
    First tries to parse with BS4, falls back to AI if needed.

    Returns:
        Contract: The parsed Contract model or None if parsing fails
    """
    # First try to extract data using the Pydantic-based XML parser
    try:
        if not xml:
            return None
        
        contract = extract_data_from_xml(xml)

        if contract:
            logging.info("Successfully extracted award data using BS4 XML parser")
            return contract

    except ValueError as e:
        logging.warning(f"Wrong notice type: {e}")
        return None
    except Exception as e:
        logging.warning(f"Pydantic parsing failed: {e}, falling back to AI")

    client = client or get_openai_client()

    completion = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": """
                    You are a public procurement assistant tasked with extracting contract award information from XML.
                    Parse the XML and extract all relevant information to create a complete contract record.
                    
                    Respond in JSON format with the following structure:
                    {
                        "notice_id": "string (required)",
                        "contract_id": "string (required)",
                        "internal_id": "string or null",
                        "issue_date": "YYYY-MM-DD or null",
                        "notice_type": "string or null",
                        "total_contract_amount": number or null,
                        "currency": "string (default EUR)",
                        "lowest_publication_amount": number or null,
                        "highest_publication_amount": number or null,
                        "number_of_publications_received": integer or null,
                        "number_of_participation_requests": integer or null,
                        "electronic_auction_used": boolean or null,
                        "dynamic_purchasing_system": "string or null",
                        "framework_agreement": "string or null",
                        "contracting_authority": {
                            "name": "string (required)",
                            "business_id": "string or null",
                            "website": "string or null",
                            "phone": "string or null",
                            "email": "string or null",
                            "company_size": "string or null",
                            "subcontracting": "string or null",
                            "address": {
                                "street": "string or null",
                                "city": "string or null",
                                "postal_code": "string or null",
                                "country": "string or null",
                                "nuts_code": "string or null"
                            },
                            "contact_persons": [
                                {
                                    "name": "string or null",
                                    "job_title": "string or null",
                                    "phone": "string or null",
                                    "email": "string or null"
                                }
                            ]
                        },
                        "winning_publisher": {
                            "name": "string (required)",
                            "business_id": "string or null",
                            "website": "string or null",
                            "phone": "string or null",
                            "email": "string or null",
                            "company_size": "string or null (look for CompanySizeCode like 'large', 'medium', 'small')",
                            "subcontracting": "string or null (look for SubcontractingTerm - if 'no' convert to 'Not applicable')",
                            "address": {same structure as above},
                            "contact_persons": [same structure as above]
                        },
                        "appeals_body": {same structure as contracting_authority} or null,
                        "service_provider": {same structure as contracting_authority} or null
                    }
                    
                    Important extraction rules:
                    - Extract IDs from the XML carefully - look for notice-id, contract folder ID, and internal references
                    - For dates, convert to YYYY-MM-DD format
                    - For amounts, extract numeric values only
                    - For organizations, include all available details including addresses and contacts
                    - For the winning publisher specifically, look for company size code and subcontracting terms
                    - Company size is typically found in efbc:CompanySizeCode elements
                    - Subcontracting info is typically found in SubcontractingTerm/TermCode elements
                """,
            },
            {
                "role": "user",
                "content": f"Extract all contract award information from this XML: {xml}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # Lower temperature for more factual extraction
    )

    try:
        result = handle_json_response_formats(completion.choices[0].message.content)

        # Parse the JSON response into Pydantic models

        # Parse date
        issue_date = None
        if "issue_date" in result and result["issue_date"]:
            try:
                issue_date = datetime.strptime(result["issue_date"], "%Y-%m-%d").date()
            except Exception as e:
                logging.warning(f"Failed to parse issue date: {e}")

        # Create Contract object
        contract_data = {
            "notice_id": result.get("notice_id", "AI-EXTRACTED"),
            "contract_id": result.get("contract_id", "AI-EXTRACTED"),
            "internal_id": result.get("internal_id"),
            "issue_date": issue_date,
            "notice_type": result.get("notice_type"),
            "total_contract_amount": result.get("total_contract_amount"),
            "currency": result.get("currency", "EUR"),
            "lowest_publication_amount": result.get("lowest_publication_amount"),
            "highest_publication_amount": result.get("highest_publication_amount"),
            "number_of_publications_received": result.get(
                "number_of_publications_received"
            ),
            "number_of_participation_requests": result.get(
                "number_of_participation_requests"
            ),
            "electronic_auction_used": result.get("electronic_auction_used"),
            "dynamic_purchasing_system": result.get("dynamic_purchasing_system"),
            "framework_agreement": result.get("framework_agreement"),
            "contracting_authority": parse_organization(
                result.get("contracting_authority", {})
            ),
            "winning_publisher": parse_organization(
                result.get("winning_publisher", {})
            ),
            "appeals_body": parse_organization(result.get("appeals_body", {})),
            "service_provider": parse_organization(result.get("service_provider", {})),
        }

        contract = ContractSchema(**contract_data)
        logging.info("Successfully extracted award data via AI")
        return contract

    except (json.JSONDecodeError, ValidationError, KeyError) as e:
        # TODO: catch the error and send mail about error
        logging.error(f"Error extracting award data via AI: {e}")
        return None


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
        model=settings.openai_model,
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

    # TODO: add scrape for publication value here and function below

    completion = client.chat.completions.create(
        model=settings.openai_model,
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

    # TODO: play with these lengths
    # Truncate XML and structured prompt if they're too long
    max_xml_length = 50000  # Reserve space for other content
    max_prompt_length = 30000

    if len(xml) > max_xml_length:
        xml = xml[:max_xml_length] + "...[XML truncated due to length]"
        logging.warning(
            f"XML content truncated for publication {publication.publication_workspace_id}"
        )

    if len(structured_prompt) > max_prompt_length:
        structured_prompt = (
            structured_prompt[:max_prompt_length]
            + "...[content truncated due to length]"
        )
        logging.warning(
            f"Structured prompt truncated for publication {publication.publication_workspace_id}"
        )

    # Create a prompt for summarization
    prompt = f"""
    Create a summary in Dutch of this procurement:
    
    {structured_prompt}

    Additional XML information: {xml}
    
    Create a concise but complete summary that describes the most important aspects of this procurement.
    """

    try:
        vector_store_id = None
        assistant_id = "asst_OMvTxo3W1byW40gTiceOzP8B"

        if filesmap:
            # Use the utility function to prepare files for the vector store
            file_objects = prepare_files_for_vector_store(filesmap=filesmap)

            if file_objects:
                vector_store = client.vector_stores.create(
                    name=f"publication_workspace_{publication.publication_workspace_id}"
                )
                vector_store_id = vector_store.id

                file_batch = client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store.id,
                    files=file_objects,
                )

                if file_batch.status != "completed":
                    logging.error("File upload failed.")
                    # Continue without files rather than failing completely
                    vector_store_id = None

        # Update assistant with vector store (or empty if no files)
        if vector_store_id:
            assistant = client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
                response_format={"type": "json_object"},
            )
        else:
            assistant = client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": []}},
                response_format={"type": "json_object"},
            )

        # Ensure the prompt isn't too long for the message
        max_message_length = 200000  # Conservative limit for message content
        if len(prompt) + len(xml) > max_message_length:
            # Further truncate if needed
            available_space = max_message_length - len(prompt) - 1000  # Buffer
            if available_space > 0:
                xml = xml[:available_space] + "...[XML further truncated]"
            else:
                xml = "[XML too long, removed]"

        final_message = (
            f"Summarize the publication and attached documents. {prompt} XML: {xml}"
        )

        # Double-check final message length
        if len(final_message) > 250000:  # Leave some buffer
            # Emergency truncation
            final_message = (
                final_message[:250000] + "...[Message truncated due to length limits]"
            )
            logging.warning(
                f"Emergency message truncation for publication {publication.publication_workspace_id}"
            )

        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": final_message,
                }
            ]
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
        )

        messages = list(
            client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id)
        )

        if not messages:
            logging.error("No response from assistant.")
            return "0", "Geen samenvatting beschikbaar.", ""

        try:
            message_content = handle_json_response_formats(
                messages[0].content[0].text.value
            )
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            logging.error(f"Error parsing assistant response: {e}")
            return "0", "Fout bij het verwerken van de samenvatting.", ""

        summary = message_content.get("summary", "Geen samenvatting beschikbaar.")
        estimated_value = message_content.get("estimated_value", 0)

        # Handle citations safely
        citations = []
        try:
            for i, ann in enumerate(messages[0].content[0].text.annotations):
                if hasattr(ann, "file_citation") and ann.file_citation:
                    try:
                        cited_file = client.files.retrieve(ann.file_citation.file_id)
                        citations.append(f"[{i}] {cited_file.filename}")
                    except Exception as cite_error:
                        logging.warning(f"Error retrieving citation file: {cite_error}")
                        citations.append(f"[{i}] Reference to document")
        except (AttributeError, IndexError) as e:
            logging.warning(f"Error processing citations: {e}")

        # Ensure we return strings, not None
        estimated_value_str = (
            str(estimated_value) if estimated_value is not None else "0"
        )
        summary_str = (
            str(summary) if summary is not None else "Geen samenvatting beschikbaar."
        )
        citations_str = "\n".join(citations) if citations else ""

        return estimated_value_str, summary_str, citations_str

    except Exception as e:
        logging.error(f"Failed to summarize files: {e}")
        # Return safe default values instead of None
        return "0", "Fout bij het genereren van samenvatting.", ""
