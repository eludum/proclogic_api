import asyncio
import logging
from io import BytesIO
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException
from openai import OpenAI

import app.crud.conversation as crud_conversation
from app.config.postgres import get_session
from app.config.settings import Settings
from app.models.company_models import Company
from app.models.conversation_models import Conversation
from app.models.publication_models import Publication
from app.util.pubproc import get_publication_workspace_documents

settings = Settings()


async def process_ai_message(
    conversation: Conversation,
    user_message: str,
    company: Company,
    publication: Publication,
    client: OpenAI,
) -> Tuple[str, Optional[str]]:
    """Process a message with OpenAI and return response and citations."""
    # Get or create OpenAI thread
    thread_id = conversation.thread_id
    assistant_id = conversation.assistant_id

    if not thread_id:
        # Create a new thread
        thread = client.beta.threads.create()
        thread_id = thread.id

        # Update conversation with thread ID
        with get_session() as session:
            crud_conversation.update_conversation_ai_info(
                conversation_id=conversation.id,
                assistant_id=assistant_id,
                thread_id=thread_id,
                session=session,
            )

    # Set up assistant if needed
    if not assistant_id:
        assistant_id = await setup_assistant(
            client=client, company=company, publication=publication
        )

        # Update conversation with assistant ID
        with get_session() as session:
            crud_conversation.update_conversation_ai_info(
                conversation_id=conversation.id,
                assistant_id=assistant_id,
                thread_id=thread_id,
                session=session,
            )

    # Add message to thread
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=user_message
    )

    # Create a run
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id
    )

    if run.status != "completed":
        return "Sorry, I had trouble processing your request. Please try again.", None

    # Get the response
    messages = list(
        client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1)
    )

    if not messages:
        return "No response was generated. Please try again.", None

    # Process response and citations
    message_content = messages[0].content[0].text
    annotations = message_content.annotations

    response_text = message_content.value
    citations = []

    # Process citations
    for index, annotation in enumerate(annotations):
        response_text = response_text.replace(annotation.text, f"[{index}]")
        if file_citation := getattr(annotation, "file_citation", None):
            try:
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")
            except Exception as e:
                logging.error(f"Error retrieving citation: {e}")
                citations.append(f"[{index}] Reference to document")

    return response_text, "\n".join(citations) if citations else None


async def stream_ai_response(
    conversation: Conversation,
    user_message: str,
    company: Company,
    publication: Publication,
    client: OpenAI,
):
    """Stream a response from OpenAI using native streaming."""
    logging.info(f"Stream AI: Starting with message: '{user_message[:30]}...'")

    # Get or create OpenAI thread and assistant
    thread_id = conversation.thread_id
    assistant_id = conversation.assistant_id

    if not thread_id:
        # Create a new thread
        thread = client.beta.threads.create()
        thread_id = thread.id
        logging.info(f"Stream AI: Created new thread {thread_id}")

        # Update conversation with thread ID
        with get_session() as session:
            crud_conversation.update_conversation_ai_info(
                conversation_id=conversation.id,
                assistant_id=assistant_id,
                thread_id=thread_id,
                session=session,
            )

    # Set up assistant if needed
    if not assistant_id:
        logging.info(f"Stream AI: Setting up new assistant for company {company.name}")
        assistant_id = await setup_assistant(
            client=client, company=company, publication=publication
        )
        logging.info(f"Stream AI: Created/found assistant {assistant_id}")

        # Update conversation with thread ID
        with get_session() as session:
            crud_conversation.update_conversation_ai_info(
                conversation_id=conversation.id,
                assistant_id=assistant_id,
                thread_id=thread_id,
                session=session,
            )

    # Check for any existing runs and wait for them to complete
    try:
        runs = client.beta.threads.runs.list(thread_id=thread_id)
        active_runs = [
            r
            for r in runs.data
            if r.status in ["queued", "in_progress", "requires_action"]
        ]

        if active_runs:
            logging.info(
                f"Stream AI: Found {len(active_runs)} active runs, waiting for completion"
            )
            active_run = active_runs[0]

            # Poll until run completes or fails
            max_wait_attempts = 30
            wait_attempts = 0
            while wait_attempts < max_wait_attempts:
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=active_run.id
                )
                status = run_status.status
                logging.info(f"Stream AI: Existing run status: {status}")

                if status in ["completed", "failed", "cancelled", "expired"]:
                    logging.info(
                        f"Stream AI: Existing run completed with status: {status}"
                    )
                    break

                await asyncio.sleep(2)
                wait_attempts += 1

            if wait_attempts >= max_wait_attempts:
                logging.error(
                    f"Stream AI: Timeout waiting for run {active_run.id} to complete"
                )
                yield "Sorry, er is een probleem met het verwerken van je bericht. Probeer het later nog eens.", []
                return
    except Exception as e:
        logging.error(f"Stream AI: Error checking for existing runs: {e}")
        # Continue anyway as this is a non-critical error

    # Add message to thread
    logging.info(f"Stream AI: Adding message to thread {thread_id}")
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=user_message
    )

    # Create a run
    logging.info(f"Stream AI: Creating run with assistant {assistant_id}")
    run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant_id
    )
    run_id = run.id
    logging.info(f"Stream AI: Run created with ID {run_id}")

    # Citations to be collected
    text_citations = []

    # # First yield an initial placeholder to start the stream
    # yield "Denken...", []

    # Poll until the run is completed
    completed = False
    error_count = 0
    max_errors = 5

    while not completed and error_count < max_errors:
        try:
            await asyncio.sleep(1)  # Poll every second

            # Check run status
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run_id
            )

            status = run_status.status
            logging.info(f"Stream AI: Run status: {status}")

            if status == "completed":
                completed = True

                # Get the response messages after run is complete
                messages = list(
                    client.beta.threads.messages.list(
                        thread_id=thread_id, order="desc", limit=1
                    )
                )

                if messages and hasattr(messages[0], "content") and messages[0].content:
                    # FIX: Properly access message content and define variables before using them
                    message_obj = messages[0].content[0]
                    if hasattr(message_obj, "text") and message_obj.text:
                        message_content = message_obj.text
                        response_text = message_content.value

                        # Process citations
                        annotations = message_content.annotations
                        for index, annotation in enumerate(annotations):
                            if hasattr(annotation, "file_citation"):
                                file_citation = annotation.file_citation
                                try:
                                    cited_file = client.files.retrieve(
                                        file_citation.file_id
                                    )
                                    text_citations.append(
                                        f"[{index}] {cited_file.filename}"
                                    )
                                except Exception as e:
                                    logging.error(f"Error retrieving citation: {e}")
                                    text_citations.append(
                                        f"[{index}] Reference to document"
                                    )

                        # Yield the complete response
                        logging.info(
                            f"Stream AI: Yielding complete response of length {len(response_text)}"
                        )
                        yield response_text, text_citations
                    else:
                        logging.error(
                            "Stream AI: Message object does not contain text content"
                        )
                        yield "Sorry, ik kon geen antwoord genereren.", []
                else:
                    logging.error(
                        "Stream AI: No message content found after completion"
                    )
                    yield "Sorry, ik kon geen antwoord genereren.", []

            elif status == "failed":
                error_message = "Er is een fout opgetreden"
                if hasattr(run_status, "last_error") and run_status.last_error:
                    error_message = run_status.last_error.message
                logging.error(f"Stream AI: Run failed: {error_message}")
                yield f"Sorry, er is een fout opgetreden: {error_message}", []
                break

            elif status == "cancelled":
                logging.info("Stream AI: Run was cancelled")
                yield "De operatie is geannuleerd.", []
                break

            elif status == "expired":
                logging.info("Stream AI: Run expired")
                yield "De operatie is verlopen.", []
                break

            elif status == "requires_action":
                # Handle action requirements if needed
                logging.info("Stream AI: Run requires action - not supported yet")
                yield "Deze operatie vereist aanvullende acties die momenteel niet worden ondersteund.", []
                break

            # Continue polling for queued or in_progress status

        except Exception as poll_error:
            error_count += 1
            logging.error(f"Stream AI: Error polling run status: {poll_error}")
            await asyncio.sleep(2)  # Wait a bit longer after an error

            if error_count >= max_errors:
                yield "Sorry, er was een probleem bij het verwerken van je verzoek na meerdere pogingen.", []

    # If we get here without yielding a response, provide a fallback
    if not completed:
        yield "Sorry, ik kon geen antwoord genereren. Probeer het later nog eens.", []


async def setup_assistant(
    client: OpenAI,
    company: Company,
    publication: Publication,
) -> str:
    """Set up an assistant for the conversation with simplified error handling."""
    try:
        # First, try to find if we already have an assistant for this company
        assistants = client.beta.assistants.list(order="desc", limit=100)

        # Use the correct naming convention as requested
        assistant_name = f"Company Assistant {company.name}"

        logging.info(f"Looking for existing assistant: {assistant_name}")

        # Look for existing assistant
        for assistant in assistants.data:
            if assistant.name == assistant_name:
                logging.info(f"Found existing assistant with ID: {assistant.id}")
                return assistant.id

        # Create a new assistant
        logging.info(f"Creating new assistant: {assistant_name}")
        assistant = client.beta.assistants.create(
            name=assistant_name,
            instructions=f"""You are an assistant helping the company {company.name} with public procurement document analysis.
            The current publication is about: {get_publication_title(publication)}
            Always respond in Dutch unless specifically asked to use another language.
            Be concise but complete in your answers. Focus on helping understand requirements, deadlines, and other important information.
            """,
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
        )
        logging.info(f"Created new assistant with ID: {assistant.id}")

        # Set up vector store with publication documents
        vector_store_id = None

        try:
            async with httpx.AsyncClient() as http_client:
                filesmap = await get_publication_workspace_documents(
                    http_client, publication.publication_workspace_id
                )

                if filesmap:
                    # Create vector store
                    vector_store = client.beta.vector_stores.create(
                        name=f"publication_{publication.publication_workspace_id}"
                    )
                    vector_store_id = vector_store.id
                    logging.info(f"Created vector store with ID: {vector_store_id}")

                    # Prepare files for upload (only accepted formats)
                    file_objects = []
                    for filename, file_data in filesmap.items():
                        if not filename.lower().endswith(
                            tuple(settings.openai_vector_store_accepted_formats)
                        ):
                            continue

                        try:
                            if hasattr(file_data, "read") and hasattr(
                                file_data, "seek"
                            ):
                                file_data.seek(0)
                                content = file_data.read()
                                byte_io = BytesIO(content)
                                byte_io.name = getattr(file_data, "name", filename)
                                file_objects.append(byte_io)
                        except Exception as e:
                            logging.error(f"Error processing file {filename}: {e}")

                    # Upload files if we have any valid ones
                    if file_objects:
                        logging.info(
                            f"Uploading {len(file_objects)} files to vector store"
                        )
                        file_batch = (
                            client.beta.vector_stores.file_batches.upload_and_poll(
                                vector_store_id=vector_store.id, files=file_objects
                            )
                        )

                        if file_batch.status == "completed":
                            # Update assistant with vector store
                            logging.info(f"Updating assistant with vector store")
                            client.beta.assistants.update(
                                assistant_id=assistant.id,
                                tool_resources={
                                    "file_search": {
                                        "vector_store_ids": [vector_store.id]
                                    }
                                },
                            )
        except Exception as e:
            logging.error(f"Error setting up vector store: {e}")
            # Continue without vector store if there was an error
            if vector_store_id:
                # Still try to update the assistant with an empty vector store
                client.beta.assistants.update(
                    assistant_id=assistant.id,
                    tool_resources={"file_search": {"vector_store_ids": []}},
                )

        return assistant.id

    except Exception as e:
        logging.error(f"Error creating assistant: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to set up AI assistant: {str(e)}"
        )


def get_publication_title(publication: Publication) -> str:
    """Extract publication title from publication object."""
    if publication and publication.dossier and publication.dossier.titles:
        for title in publication.dossier.titles:
            if title.language in settings.prefered_languages_descriptions:
                return title.text
    return "Untitled Publication"
