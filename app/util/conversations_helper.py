import asyncio
import logging
from typing import Optional, Tuple, List, Dict

from openai import OpenAI

from app.config.settings import settings
from app.models.company_models import Company
from app.models.conversation_models import Conversation
from app.models.publication_models import Publication
from app.util.publication_utils.publication_converter import PublicationConverter


def build_conversation_history(conversation: Conversation, company: Company, publication: Publication) -> List[Dict[str, str]]:
    """Build conversation history from database messages with system prompt."""
    pub_data = PublicationConverter.to_output_schema(publication, company)

    system_message = f"""You are an AI assistant helping {company.name} with public procurement document analysis for tender {pub_data.title}.

PUBLICATION INFORMATION:
- Title: {pub_data.title}
- Organization: {pub_data.organisation}
- Submission deadline: {pub_data.submission_deadline}
- CPV code: {pub_data.cpv_code}
- Sector: {pub_data.sector}
- Estimated value: {pub_data.estimated_value if pub_data.estimated_value else "Unknown"}

COMPANY INFORMATION:
- VAT: {company.vat_number}
- Activities: {company.summary_activities}
- Interested sectors: {', '.join(sector.sector for sector in company.interested_sectors)}
- Accreditations: {company.accreditations if company.accreditations else 'None'}
- Regions: {', '.join(company.operating_regions) if company.operating_regions else 'Not specified'}

GUIDELINES:
- Always respond in Dutch unless specifically asked to use another language
- Be concise but complete in your answers
- Focus on helping the company understand the publication requirements, deadlines, and eligibility
- Provide advice tailored to this company's profile and capabilities
- If you reference documents, cite the source clearly
"""

    messages = [{"role": "system", "content": system_message}]

    # Add conversation history
    for msg in sorted(conversation.messages, key=lambda m: m.created_at):
        messages.append({"role": msg.role, "content": msg.content})

    return messages


async def process_ai_message(
    conversation: Conversation,
    user_message: str,
    company: Company,
    publication: Publication,
    client: OpenAI,
) -> Tuple[str, Optional[str]]:
    """Process a message with OpenAI Chat Completions API and return response."""
    # Build conversation history
    messages = build_conversation_history(conversation, company, publication)

    # Add the new user message
    messages.append({"role": "user", "content": user_message})

    # Call Chat Completions API
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
    )

    response_text = response.choices[0].message.content

    # No citations in standard chat completions
    return response_text, None


# TODO: fix streaming to be true streaming (see SDK)
async def stream_ai_response(
    conversation: Conversation,
    user_message: str,
    company: Company,
    publication: Publication,
    client: OpenAI,
):
    """Stream a response from OpenAI using Chat Completions API streaming."""
    logging.info(f"Stream AI: Starting with message: '{user_message[:30]}...'")

    try:
        # Build conversation history
        messages = build_conversation_history(conversation, company, publication)

        # Add the new user message
        messages.append({"role": "user", "content": user_message})

        # Create streaming response - use async loop to prevent blocking
        stream = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            stream=True,
        )

        # Stream the response
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                # Yield each chunk as it comes
                yield content, []
                # Allow other tasks to run
                await asyncio.sleep(0)

        logging.info(f"Stream AI: Completed streaming response")

    except Exception as e:
        logging.error(f"Stream AI: Error during streaming: {e}")
        yield "Sorry, er is een fout opgetreden bij het verwerken van je verzoek.", []


def get_publication_title(publication: Publication) -> str:
    """Extract publication title from publication object."""
    if publication and publication.dossier and publication.dossier.titles:
        for title in publication.dossier.titles:
            if title.language in settings.prefered_languages_descriptions:
                return title.text
    return "Untitled Publication"
