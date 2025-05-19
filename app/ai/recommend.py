import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, Optional

from openai import OpenAI

from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.schemas.analytics_schemas import (
    AddressCreate,
    AppealsBodyContactCreate,
    AppealsBodyCreate,
    AwardCreate,
    AwardSupplierCreate,
    ContactCreate,
    OrganizationCreate,
    WinnerCreate,
)
from app.schemas.company_schemas import CompanySchema
from app.schemas.publication_schemas import PublicationSchema
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.redis_utils import prepare_files_for_vector_store

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


def parse_datetime(date_str: str) -> Optional[datetime]:
    """Parse date string to datetime object"""
    if not date_str:
        return None

    try:
        # Handle various date formats
        if "T" in date_str:
            # ISO format with timezone
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        elif "+" in date_str:
            # Format like "2025-05-16+02:00"
            parts = date_str.split("+")
            date_part = parts[0]
            return datetime.fromisoformat(date_part)
        else:
            # Simple date format
            return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception as e:
        logging.warning(f"Error parsing date {date_str}: {e}")
        return None


def extract_award_data_from_xml(xml_content: str) -> Dict[str, Any]:
    """
    Extract award data from XML content using ElementTree.
    Returns a dictionary with structured objects ready for database insertion.
    """
    if not xml_content:
        return {}

    try:
        # Parse XML content
        root = ET.fromstring(xml_content)

        # Define namespaces (from the XML example)
        namespaces = {
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
            "efbc": "http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1",
        }

        # Initialize structured objects
        award_data = {}
        winner_data = {}
        winner_address = {}
        organization_data = {}
        organization_address = {}
        organization_contact = {}
        appeals_body_data = {}
        appeals_body_address = {}
        appeals_body_contact = {}
        suppliers_data = []

        # Basic Information
        try:
            # Notice ID
            notice_id_element = root.find(
                ".//cbc:ID[@schemeName='notice-id']", namespaces
            )
            if notice_id_element is not None:
                award_data["notice_id"] = notice_id_element.text

            # Contract ID
            contract_id_element = root.find(".//cbc:ContractFolderID", namespaces)
            if contract_id_element is not None:
                award_data["contract_id"] = contract_id_element.text

            # Internal ID
            internal_id_element = root.find(
                ".//cac:ProcurementProject/cbc:ID[@schemeName='InternalID']", namespaces
            )
            if internal_id_element is not None:
                award_data["internal_id"] = internal_id_element.text

            # Issue Date
            issue_date_element = root.find(".//cbc:IssueDate", namespaces)
            if issue_date_element is not None:
                award_data["issue_date"] = parse_datetime(issue_date_element.text)

            # Notice Type
            notice_type_element = root.find(".//cbc:NoticeTypeCode", namespaces)
            if notice_type_element is not None:
                award_data["notice_type"] = notice_type_element.text
        except Exception as e:
            logging.warning(f"Error extracting basic information: {e}")

        # Extract award value
        try:
            # Total Amount
            amount_element = root.find(".//cbc:TotalAmount", namespaces)
            if amount_element is not None:
                award_data["award_value"] = float(amount_element.text)
                if "currencyID" in amount_element.attrib:
                    award_data["currency"] = amount_element.attrib["currencyID"]

            # Lowest Tender Amount
            lower_tender_element = root.find(".//cbc:LowerTenderAmount", namespaces)
            if lower_tender_element is not None:
                award_data["lowest_tender_amount"] = float(lower_tender_element.text)
                if "currencyID" in lower_tender_element.attrib:
                    award_data["currency"] = lower_tender_element.attrib["currencyID"]

            # Highest Tender Amount
            higher_tender_element = root.find(".//cbc:HigherTenderAmount", namespaces)
            if higher_tender_element is not None:
                award_data["highest_tender_amount"] = float(higher_tender_element.text)
                if "currencyID" in higher_tender_element.attrib:
                    award_data["currency"] = higher_tender_element.attrib["currencyID"]
        except Exception as e:
            logging.warning(f"Error extracting financial information: {e}")

        # Extract award date
        try:
            award_date_element = root.find(".//cbc:AwardDate", namespaces)
            if award_date_element is not None:
                award_data["award_date"] = parse_datetime(award_date_element.text)
        except Exception as e:
            logging.warning(f"Error extracting award date: {e}")

        # Extract Tender Process Information
        try:
            # Number of Tenders Received
            stats_elements = root.findall(
                ".//efac:ReceivedSubmissionsStatistics", namespaces
            )
            for stats_element in stats_elements:
                stats_code = stats_element.find("./efbc:StatisticsCode", namespaces)
                stats_num = stats_element.find("./efbc:StatisticsNumeric", namespaces)

                if stats_code is not None and stats_num is not None:
                    code_value = stats_code.text
                    if code_value == "tenders":
                        award_data["tenders_received"] = int(stats_num.text)
                    elif code_value == "part-req":
                        award_data["participation_requests"] = int(stats_num.text)

            # Electronic Auction Used
            auction_element = root.find(".//cbc:AuctionConstraintIndicator", namespaces)
            if auction_element is not None:
                award_data["electronic_auction_used"] = (
                    auction_element.text.lower() == "true"
                )

            # Dynamic Purchasing System
            dps_element = root.find(
                ".//cbc:ContractingSystemTypeCode[@listName='dps-usage']", namespaces
            )
            if dps_element is not None:
                award_data["dynamic_purchasing_system"] = dps_element.text

            # Framework Agreement
            framework_element = root.find(
                ".//cbc:ContractingSystemTypeCode[@listName='framework-agreement']",
                namespaces,
            )
            if framework_element is not None:
                award_data["framework_agreement"] = framework_element.text
        except Exception as e:
            logging.warning(f"Error extracting tender process information: {e}")

        # Extract contract details
        try:
            contract_element = root.find(".//efac:SettledContract", namespaces)
            if contract_element is not None:
                ref_element = contract_element.find(
                    "./efac:ContractReference/cbc:ID", namespaces
                )
                if ref_element is not None:
                    award_data["contract_reference"] = ref_element.text

                title_element = contract_element.find("./cbc:Title", namespaces)
                if title_element is not None:
                    award_data["contract_title"] = title_element.text

                issue_date_element = contract_element.find(
                    "./cbc:IssueDate", namespaces
                )
                if issue_date_element is not None:
                    award_data["contract_start_date"] = parse_datetime(
                        issue_date_element.text
                    )

            # Extract contract period
            period_element = root.find(".//cac:PlannedPeriod", namespaces)
            if period_element is not None:
                start_date_element = period_element.find("./cbc:StartDate", namespaces)
                if start_date_element is not None:
                    award_data["contract_start_date"] = parse_datetime(
                        start_date_element.text
                    )

                end_date_element = period_element.find("./cbc:EndDate", namespaces)
                if end_date_element is not None:
                    award_data["contract_end_date"] = parse_datetime(
                        end_date_element.text
                    )
        except Exception as e:
            logging.warning(f"Error extracting contract details: {e}")

        # Extract winner information with enhanced details
        try:
            # Find winning organization
            tender_id = None
            lot_tender_element = root.find(".//efac:LotTender", namespaces)
            if lot_tender_element is not None:
                tender_id_element = lot_tender_element.find("./cbc:ID", namespaces)
                if tender_id_element is not None:
                    tender_id = tender_id_element.text

            if tender_id:
                # Find the tendering party
                tendering_party_element = root.find(
                    f".//efac:TenderingParty[./cbc:ID[text()='{tender_id}']]",
                    namespaces,
                )
                if not tendering_party_element:
                    tendering_party_element = root.find(
                        f".//efac:TenderingParty", namespaces
                    )

                if tendering_party_element:
                    # Extract tender reference
                    tender_ref_element = root.find(
                        f".//efac:TenderReference/cbc:ID", namespaces
                    )
                    if tender_ref_element is not None:
                        winner_data["tender_reference"] = tender_ref_element.text

                    # Get tenderer organization reference
                    tenderer_element = tendering_party_element.find(
                        "./efac:Tenderer", namespaces
                    )
                    if tenderer_element:
                        org_id_element = tenderer_element.find("./cbc:ID", namespaces)
                        if org_id_element is not None:
                            org_id = org_id_element.text

                            # Find organization with this ID
                            org_xpath = f".//efac:Organizations/efac:Organization/efac:Company[./cac:PartyIdentification/cbc:ID[text()='{org_id}']]"
                            org_element = root.find(org_xpath, namespaces)

                            if org_element:
                                # Extract organization name
                                name_element = org_element.find(
                                    "./cac:PartyName/cbc:Name", namespaces
                                )
                                if name_element is not None:
                                    winner_data["name"] = name_element.text

                                # Extract VAT number
                                vat_element = org_element.find(
                                    "./cac:PartyLegalEntity/cbc:CompanyID", namespaces
                                )
                                if vat_element is not None:
                                    winner_data["vat_number"] = (
                                        vat_element.text.replace(" ", "")
                                    )

                                # Extract email
                                email_element = org_element.find(
                                    "./cac:Contact/cbc:ElectronicMail", namespaces
                                )
                                if email_element is not None:
                                    winner_data["email"] = email_element.text

                                # Extract phone
                                phone_element = org_element.find(
                                    "./cac:Contact/cbc:Telephone", namespaces
                                )
                                if phone_element is not None:
                                    winner_data["phone"] = phone_element.text

                                # Extract website
                                website_element = org_element.find(
                                    "./cbc:WebsiteURI", namespaces
                                )
                                if website_element is not None:
                                    winner_data["website"] = website_element.text

                                # Extract company size
                                size_element = org_element.find(
                                    "./efbc:CompanySizeCode", namespaces
                                )
                                if size_element is not None:
                                    winner_data["size"] = size_element.text

                                # Extract address
                                address_element = org_element.find(
                                    "./cac:PostalAddress", namespaces
                                )
                                if address_element is not None:
                                    street_element = address_element.find(
                                        "./cbc:StreetName", namespaces
                                    )
                                    if street_element is not None:
                                        winner_address["street"] = street_element.text

                                    city_element = address_element.find(
                                        "./cbc:CityName", namespaces
                                    )
                                    if city_element is not None:
                                        winner_address["city"] = city_element.text

                                    postal_element = address_element.find(
                                        "./cbc:PostalZone", namespaces
                                    )
                                    if postal_element is not None:
                                        winner_address["postal_code"] = (
                                            postal_element.text
                                        )

                                    nuts_element = address_element.find(
                                        "./cbc:CountrySubentityCode", namespaces
                                    )
                                    if nuts_element is not None:
                                        winner_address["nuts_code"] = nuts_element.text

                                    country_element = address_element.find(
                                        "./cac:Country/cbc:IdentificationCode",
                                        namespaces,
                                    )
                                    if country_element is not None:
                                        winner_address["country_code"] = (
                                            country_element.text
                                        )

                            # Extract subcontracting information
                            subcontract_element = root.find(
                                ".//efac:SubcontractingTerm/efbc:TermCode", namespaces
                            )
                            if subcontract_element is not None:
                                winner_data["subcontracting"] = subcontract_element.text
        except Exception as e:
            logging.warning(f"Error extracting winner information: {e}")

        # Extract organization information (contracting authority)
        try:
            contracting_org_element = root.find(
                ".//cac:ContractingParty/cac:Party/cac:PartyIdentification/cbc:ID",
                namespaces,
            )
            if contracting_org_element is not None:
                org_id = contracting_org_element.text

                # Find organization with this ID
                org_xpath = f".//efac:Organizations/efac:Organization/efac:Company[./cac:PartyIdentification/cbc:ID[text()='{org_id}']]"
                org_element = root.find(org_xpath, namespaces)

                if org_element:
                    # Extract organization name
                    name_element = org_element.find(
                        "./cac:PartyName/cbc:Name", namespaces
                    )
                    if name_element is not None:
                        organization_data["name"] = name_element.text

                    # Extract VAT number
                    vat_element = org_element.find(
                        "./cac:PartyLegalEntity/cbc:CompanyID", namespaces
                    )
                    if vat_element is not None:
                        organization_data["vat_number"] = vat_element.text.replace(
                            " ", ""
                        )

                    # Extract website
                    website_element = org_element.find("./cbc:WebsiteURI", namespaces)
                    if website_element is not None:
                        organization_data["website"] = website_element.text

                    # Extract contact details
                    contact_element = org_element.find("./cac:Contact", namespaces)
                    if contact_element is not None:
                        name_element = contact_element.find("./cbc:Name", namespaces)
                        if name_element is not None:
                            organization_contact["name"] = name_element.text

                        job_title_element = contact_element.find(
                            "./cbc:JobTitle", namespaces
                        )
                        if job_title_element is not None:
                            organization_contact["job_title"] = job_title_element.text

                        phone_element = contact_element.find(
                            "./cbc:Telephone", namespaces
                        )
                        if phone_element is not None:
                            organization_contact["phone"] = phone_element.text

                        email_element = contact_element.find(
                            "./cbc:ElectronicMail", namespaces
                        )
                        if email_element is not None:
                            organization_contact["email"] = email_element.text

                    # Extract address
                    address_element = org_element.find(
                        "./cac:PostalAddress", namespaces
                    )
                    if address_element is not None:
                        street_element = address_element.find(
                            "./cbc:StreetName", namespaces
                        )
                        if street_element is not None:
                            organization_address["street"] = street_element.text

                        city_element = address_element.find(
                            "./cbc:CityName", namespaces
                        )
                        if city_element is not None:
                            organization_address["city"] = city_element.text

                        postal_element = address_element.find(
                            "./cbc:PostalZone", namespaces
                        )
                        if postal_element is not None:
                            organization_address["postal_code"] = postal_element.text

                        nuts_element = address_element.find(
                            "./cbc:CountrySubentityCode", namespaces
                        )
                        if nuts_element is not None:
                            organization_address["nuts_code"] = nuts_element.text

                        country_element = address_element.find(
                            "./cac:Country/cbc:IdentificationCode", namespaces
                        )
                        if country_element is not None:
                            organization_address["country_code"] = country_element.text
        except Exception as e:
            logging.warning(f"Error extracting organization information: {e}")

        # Extract appeals body information
        try:
            appeals_org_element = root.find(
                ".//cac:AppealTerms/cac:AppealReceiverParty/cac:PartyIdentification/cbc:ID",
                namespaces,
            )
            if appeals_org_element is not None:
                org_id = appeals_org_element.text

                # Find organization with this ID
                org_xpath = f".//efac:Organizations/efac:Organization/efac:Company[./cac:PartyIdentification/cbc:ID[text()='{org_id}']]"
                org_element = root.find(org_xpath, namespaces)

                if org_element:
                    # Extract name
                    name_element = org_element.find(
                        "./cac:PartyName/cbc:Name", namespaces
                    )
                    if name_element is not None:
                        appeals_body_data["name"] = name_element.text

                    # Extract VAT number
                    vat_element = org_element.find(
                        "./cac:PartyLegalEntity/cbc:CompanyID", namespaces
                    )
                    if vat_element is not None:
                        appeals_body_data["vat_number"] = vat_element.text.replace(
                            " ", ""
                        )

                    # Extract website
                    website_element = org_element.find("./cbc:WebsiteURI", namespaces)
                    if website_element is not None:
                        appeals_body_data["website"] = website_element.text

                    # Extract contact details
                    contact_element = org_element.find("./cac:Contact", namespaces)
                    if contact_element is not None:
                        phone_element = contact_element.find(
                            "./cbc:Telephone", namespaces
                        )
                        if phone_element is not None:
                            appeals_body_contact["phone"] = phone_element.text

                        email_element = contact_element.find(
                            "./cbc:ElectronicMail", namespaces
                        )
                        if email_element is not None:
                            appeals_body_contact["email"] = email_element.text

                    # Extract address
                    address_element = org_element.find(
                        "./cac:PostalAddress", namespaces
                    )
                    if address_element is not None:
                        street_element = address_element.find(
                            "./cbc:StreetName", namespaces
                        )
                        if street_element is not None:
                            appeals_body_address["street"] = street_element.text

                        city_element = address_element.find(
                            "./cbc:CityName", namespaces
                        )
                        if city_element is not None:
                            appeals_body_address["city"] = city_element.text

                        postal_element = address_element.find(
                            "./cbc:PostalZone", namespaces
                        )
                        if postal_element is not None:
                            appeals_body_address["postal_code"] = postal_element.text

                        nuts_element = address_element.find(
                            "./cbc:CountrySubentityCode", namespaces
                        )
                        if nuts_element is not None:
                            appeals_body_address["nuts_code"] = nuts_element.text

                        country_element = address_element.find(
                            "./cac:Country/cbc:IdentificationCode", namespaces
                        )
                        if country_element is not None:
                            appeals_body_address["country_code"] = country_element.text
        except Exception as e:
            logging.warning(f"Error extracting appeals body information: {e}")

        # Extract suppliers (other than winner)
        try:
            # Find all organizations
            org_elements = root.findall(
                ".//efac:Organizations/efac:Organization/efac:Company", namespaces
            )

            for org_element in org_elements:
                # Skip if this is the winner
                if winner_data and "name" in winner_data:
                    name_element = org_element.find(
                        "./cac:PartyName/cbc:Name", namespaces
                    )
                    if (
                        name_element is not None
                        and name_element.text == winner_data["name"]
                    ):
                        continue

                # Skip if this is the contracting authority
                if organization_data and "name" in organization_data:
                    name_element = org_element.find(
                        "./cac:PartyName/cbc:Name", namespaces
                    )
                    if (
                        name_element is not None
                        and name_element.text == organization_data["name"]
                    ):
                        continue

                # Skip if this is the appeals body
                if appeals_body_data and "name" in appeals_body_data:
                    name_element = org_element.find(
                        "./cac:PartyName/cbc:Name", namespaces
                    )
                    if (
                        name_element is not None
                        and name_element.text == appeals_body_data["name"]
                    ):
                        continue

                supplier = {}
                supplier_address = {}

                # Extract name
                name_element = org_element.find("./cac:PartyName/cbc:Name", namespaces)
                if name_element is not None:
                    supplier["name"] = name_element.text
                else:
                    # Skip if no name
                    continue

                # Extract VAT number
                vat_element = org_element.find(
                    "./cac:PartyLegalEntity/cbc:CompanyID", namespaces
                )
                if vat_element is not None:
                    supplier["vat_number"] = vat_element.text.replace(" ", "")

                # Extract email
                email_element = org_element.find(
                    "./cac:Contact/cbc:ElectronicMail", namespaces
                )
                if email_element is not None:
                    supplier["email"] = email_element.text

                # Extract phone
                phone_element = org_element.find(
                    "./cac:Contact/cbc:Telephone", namespaces
                )
                if phone_element is not None:
                    supplier["phone"] = phone_element.text

                # Extract website
                website_element = org_element.find("./cbc:WebsiteURI", namespaces)
                if website_element is not None:
                    supplier["website"] = website_element.text

                # Extract address
                address_element = org_element.find("./cac:PostalAddress", namespaces)
                if address_element is not None:
                    street_element = address_element.find(
                        "./cbc:StreetName", namespaces
                    )
                    if street_element is not None:
                        supplier_address["street"] = street_element.text

                    city_element = address_element.find("./cbc:CityName", namespaces)
                    if city_element is not None:
                        supplier_address["city"] = city_element.text

                    postal_element = address_element.find(
                        "./cbc:PostalZone", namespaces
                    )
                    if postal_element is not None:
                        supplier_address["postal_code"] = postal_element.text

                    nuts_element = address_element.find(
                        "./cbc:CountrySubentityCode", namespaces
                    )
                    if nuts_element is not None:
                        supplier_address["nuts_code"] = nuts_element.text

                    country_element = address_element.find(
                        "./cac:Country/cbc:IdentificationCode", namespaces
                    )
                    if country_element is not None:
                        supplier_address["country_code"] = country_element.text

                # Only add address if it has data
                if supplier_address:
                    supplier["address"] = AddressCreate(**supplier_address)

                suppliers_data.append(supplier)
        except Exception as e:
            logging.warning(f"Error extracting suppliers: {e}")

        # Build structured objects
        result = {"award_data": award_data, "xml_content": xml_content}

        # Add winner if we have data
        if winner_data:
            # Add address if we have it
            if winner_address:
                winner_data["address"] = AddressCreate(**winner_address)
            result["winner"] = WinnerCreate(**winner_data)

        # Add organization if we have data
        if organization_data:
            # Add address if we have it
            if organization_address:
                organization_data["address"] = AddressCreate(**organization_address)
            # Add contact if we have it
            if organization_contact:
                organization_data["contact"] = ContactCreate(**organization_contact)
            result["organization"] = OrganizationCreate(**organization_data)

        # Add appeals body if we have data
        if appeals_body_data:
            # Add address if we have it
            if appeals_body_address:
                appeals_body_data["address"] = AddressCreate(**appeals_body_address)
            # Add contact if we have it
            if appeals_body_contact:
                appeals_body_data["contact"] = AppealsBodyContactCreate(
                    **appeals_body_contact
                )
            result["appeals_body"] = AppealsBodyCreate(**appeals_body_data)

        # Add suppliers if we have any
        if suppliers_data:
            result["suppliers"] = [
                AwardSupplierCreate(**supplier) for supplier in suppliers_data
            ]

        return result
    except Exception as e:
        logging.error(f"Failed to parse XML with ElementTree: {e}")
        return {}


def summarize_publication_award(xml: str, client: OpenAI = None) -> Dict[str, Any]:
    """
    Extract award information from publication XML using AI.
    Used as a fallback when the XML parser fails.

    Returns structured data suitable for creating database records.
    """
    # Initialize the OpenAI client if not provided
    client = client or get_openai_client()

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": """
                        You are a public procurement assistant tasked with summarizing the award of a publication.
                        Extract detailed information from the XML.
                        If multiple values exist, choose the primary one.
                        
                        Respond in JSON with nested structures for related entities like addresses, contacts, etc.
                        
                        The response should have this structure:
                        {
                          "award_data": {
                            "notice_id": string,
                            "contract_id": string,
                            "internal_id": string,
                            "issue_date": string,  // YYYY-MM-DD format
                            "notice_type": string,
                            
                            "award_date": string,  // YYYY-MM-DD format
                            "award_value": number,
                            "lowest_tender_amount": number,
                            "highest_tender_amount": number,
                            "currency": string,
                            
                            "tenders_received": number,
                            "participation_requests": number,
                            "electronic_auction_used": boolean,
                            "dynamic_purchasing_system": string,
                            "framework_agreement": string,
                            
                            "contract_reference": string,
                            "contract_title": string,
                            "contract_start_date": string,  // YYYY-MM-DD format
                            "contract_end_date": string  // YYYY-MM-DD format
                          },
                          
                          "winner": {
                            "name": string,
                            "vat_number": string,
                            "email": string,
                            "phone": string,
                            "website": string,
                            "size": string,
                            "tender_reference": string,
                            "subcontracting": string,
                            "address": {
                              "street": string,
                              "city": string,
                              "postal_code": string,
                              "nuts_code": string,
                              "country_code": string
                            }
                          },
                          
                          "organization": {
                            "name": string,
                            "vat_number": string,
                            "website": string,
                            "contact": {
                              "name": string,
                              "job_title": string,
                              "phone": string,
                              "email": string
                            },
                            "address": {
                              "street": string,
                              "city": string,
                              "postal_code": string,
                              "nuts_code": string,
                              "country_code": string
                            }
                          },
                          
                          "appeals_body": {
                            "name": string,
                            "vat_number": string,
                            "website": string,
                            "contact": {
                              "phone": string,
                              "email": string
                            },
                            "address": {
                              "street": string,
                              "city": string,
                              "postal_code": string,
                              "nuts_code": string,
                              "country_code": string
                            }
                          },
                          
                          "suppliers": [
                            {
                              "name": string,
                              "vat_number": string,
                              "email": string,
                              "phone": string,
                              "website": string,
                              "address": {
                                "street": string,
                                "city": string,
                                "postal_code": string,
                                "nuts_code": string,
                                "country_code": string
                              }
                            }
                          ]
                        }
                    """,
                },
                {
                    "role": "user",
                    "content": f"Extract the complete award information from this XML: {xml}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,  # Lower temperature for more factual extraction
        )

        # Parse the response
        ai_response = handle_json_response_formats(
            completion.choices[0].message.content
        )

        # Convert the flat JSON response into our structured Pydantic models
        result = {}

        # Process award data
        if "award_data" in ai_response:
            result["award_data"] = ai_response["award_data"]

        # Process winner data
        if "winner" in ai_response:
            winner_data = ai_response["winner"]
            address_data = None

            if "address" in winner_data:
                address_data = AddressCreate(**winner_data.pop("address"))

            winner = WinnerCreate(**winner_data)
            if address_data:
                winner.address = address_data

            result["winner"] = winner

        # Process organization data
        if "organization" in ai_response:
            org_data = ai_response["organization"]
            address_data = None
            contact_data = None

            if "address" in org_data:
                address_data = AddressCreate(**org_data.pop("address"))

            if "contact" in org_data:
                contact_data = ContactCreate(**org_data.pop("contact"))

            organization = OrganizationCreate(**org_data)
            if address_data:
                organization.address = address_data
            if contact_data:
                organization.contact = contact_data

            result["organization"] = organization

        # Process appeals body data
        if "appeals_body" in ai_response:
            appeals_data = ai_response["appeals_body"]
            address_data = None
            contact_data = None

            if "address" in appeals_data:
                address_data = AddressCreate(**appeals_data.pop("address"))

            if "contact" in appeals_data:
                contact_data = AppealsBodyContactCreate(**appeals_data.pop("contact"))

            appeals_body = AppealsBodyCreate(**appeals_data)
            if address_data:
                appeals_body.address = address_data
            if contact_data:
                appeals_body.contact = contact_data

            result["appeals_body"] = appeals_body

        # Process suppliers data
        if "suppliers" in ai_response and isinstance(ai_response["suppliers"], list):
            suppliers = []

            for supplier_data in ai_response["suppliers"]:
                address_data = None

                if "address" in supplier_data:
                    address_data = AddressCreate(**supplier_data.pop("address"))

                supplier = AwardSupplierCreate(**supplier_data)
                if address_data:
                    supplier.address = address_data

                suppliers.append(supplier)

            if suppliers:
                result["suppliers"] = suppliers

        return result
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Error extracting award data via AI: {e}")
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

    # Create a prompt for summarization
    prompt = f"""
    Create a summary in Dutch of this procurement:
    
    {structured_prompt}

    Additional XML information: {xml}
    
    Create a concise but complete summary that describes the most important aspects of this procurement. If a document contains an estimated value of the publication, make sure to populate the estimated_value field.
    """
    try:
        if filesmap:
            # Use the utility function to prepare files for the vector store
            file_objects = prepare_files_for_vector_store(filesmap=filesmap)

            if file_objects:
                vector_store = client.vector_stores.create(
                    name=f"publication_workspace_{publication.publication_workspace_id}"
                )

                file_batch = client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store.id,
                    files=file_objects,
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
            thread_id=thread.id,
            assistant_id=assistant.id,
        )
        messages = list(
            client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id)
        )

        if not messages:
            logging.error("No response from assistant.")
            return None, None, None

        message_content = handle_json_response_formats(
            messages[0].content[0].text.value
        )

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
