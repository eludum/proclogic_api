import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel
from redis.client import Redis

import app.crud.company as crud_company
from app.ai.openai import get_openai_client
from app.config.postgres import get_session
from app.config.settings import Settings
from app.config.redis_manager import get_redis_client
from app.crud.agent import RedisAgentStorage
from app.util.pubproc import get_publication_workspace_documents

conversations_router = APIRouter()

settings = Settings()


class ConversationRequest(BaseModel):
    publication_id: str
    vat_number: str  # Added VAT number to identify the company
    message: str
    thread_id: Optional[str] = None  # For continuing conversations


class ConversationResponse(BaseModel):
    thread_id: str
    response: str
    citations: List[str]


# Dependency to get Redis agent storage
def get_agent_storage(redis: Redis = Depends(get_redis_client)):
    return RedisAgentStorage(redis)


@conversations_router.post("/conversation", response_model=ConversationResponse)
async def conversation_with_files(
    request: ConversationRequest,
    background_tasks: BackgroundTasks,
    client: OpenAI = Depends(get_openai_client),
    agent_storage: RedisAgentStorage = Depends(get_agent_storage),
):
    """
    API endpoint to have a conversation with procurement files.
    Allows users to ask questions about the files and get responses.
    Creates agents per company (identified by VAT number).
    """
    try:
        # TODO: give all info about the publication, not just the files
        # store chat data longer, make list of chats
        vat_number = request.vat_number
        publication_id = request.publication_id
        thread_id = request.thread_id

        # Verify the company exists
        with get_session() as session:
            company = crud_company.get_company_by_vat_number(
                vat_number=vat_number, session=session
            )

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Check if we already have an active agent for this company
        assistant_id = agent_storage.get_company_assistant_id(vat_number)

        if not assistant_id:
            # Create a new assistant for this company
            assistant = client.beta.assistants.create(
                name=f"Company Assistant {company.name}",
                instructions=f"You are an assistant for {company.name}. Help with procurement files analysis.",
                model="gpt-4-turbo",
                tools=[{"type": "file_search"}],
            )

            # Store the assistant ID in Redis
            agent_storage.store_company_assistant(vat_number, assistant.id)
            assistant_id = assistant.id

        # Check if we're starting a new conversation for this publication
        if not thread_id and agent_storage.publication_exists(
            vat_number, publication_id
        ):
            # Clean up the old session if starting a new conversation
            background_tasks.add_task(
                cleanup_publication_session,
                vat_number,
                publication_id,
                client,
                agent_storage,
            )
            # Delete immediately to prevent conflicts
            agent_storage.delete_publication_data(vat_number, publication_id)

        # If no thread_id is provided or the publication isn't active, create a new session
        if not thread_id or not agent_storage.publication_exists(
            vat_number, publication_id
        ):
            # Fetch documents for this publication
            async with httpx.AsyncClient() as http_client:
                filesmap = await get_publication_workspace_documents(
                    http_client, publication_id
                )

            # Create a new vector store
            vector_store = client.beta.vector_stores.create(
                name=f"company_{vat_number}_publication_{publication_id}"
            )

            # Filter files with the right extensions
            filesmap = {
                file_name: file_data
                for file_name, file_data in filesmap.items()
                if file_name.lower().endswith(
                    tuple(settings.openai_vector_store_accepted_formats)
                )
            }

            # Upload files to the vector store
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id,
                files=[file_data for file_data in filesmap.values()],
            )

            # Wait for file processing to complete
            while file_batch.status != "completed":
                if file_batch.status == "failed":
                    logging.error(
                        f"Failed to upload files to vector store: {file_batch}"
                    )
                    raise HTTPException(
                        status_code=500, detail="Failed to process files"
                    )
                if file_batch.status == "in_progress":
                    continue

            # Update the assistant with the new vector store
            client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
            )

            # Create a new thread for this conversation
            thread = client.beta.threads.create(
                messages=[
                    {
                        "role": "user",
                        "content": request.message,
                    }
                ]
            )
            thread_id = thread.id

            # Store the session information in Redis
            agent_storage.store_publication_data(
                vat_number, publication_id, vector_store.id, thread_id
            )

        else:
            # Continue an existing conversation
            publication_data = agent_storage.get_publication_data(
                vat_number, publication_id
            )

            # If thread_id is provided, verify it matches what we have stored
            if thread_id and publication_data.get("thread_id") != thread_id:
                raise HTTPException(
                    status_code=404,
                    detail="Thread not found for this publication and company",
                )

            # Use the thread_id from storage if not provided
            if not thread_id:
                thread_id = publication_data.get("thread_id")

            # Add the new message to the existing thread
            client.beta.threads.messages.create(
                thread_id=thread_id, role="user", content=request.message
            )

            # Refresh TTL for this company and publication
            agent_storage.refresh_ttl(vat_number, publication_id)

        # Create and poll the run
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=assistant_id
        )

        # Get the assistant's response messages
        messages = list(
            client.beta.threads.messages.list(
                thread_id=thread_id,
                order="desc",  # Get most recent first
                limit=1,  # Only get the last message
            )
        )

        # Process the response message and citations
        message_content = messages[0].content[0].text
        annotations = message_content.annotations
        citations = []

        # Process citations and annotations
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f"[{index}]"
            )
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        return ConversationResponse(
            thread_id=thread_id, response=message_content.value, citations=citations
        )

    except Exception as e:
        logging.error(f"Error in conversation endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@conversations_router.delete("/conversation/{vat_number}/{publication_id}")
async def end_conversation(
    vat_number: str,
    publication_id: str,
    client: OpenAI = Depends(get_openai_client),
    agent_storage: RedisAgentStorage = Depends(get_agent_storage),
):
    """
    End a conversation and clean up resources for a specific publication and company.
    """
    if not agent_storage.publication_exists(vat_number, publication_id):
        raise HTTPException(
            status_code=404,
            detail="No active conversation for this publication and company",
        )

    await cleanup_publication_session(vat_number, publication_id, client, agent_storage)
    return {"message": "Conversation ended and resources cleaned up"}


@conversations_router.delete("/conversation/company/{vat_number}")
async def cleanup_company(
    vat_number: str,
    client: OpenAI = Depends(get_openai_client),
    agent_storage: RedisAgentStorage = Depends(get_agent_storage),
):
    """
    Clean up all resources for a company.
    """
    if not agent_storage.company_exists(vat_number):
        raise HTTPException(status_code=404, detail="No active agent for this company")

    await cleanup_company_agent(vat_number, client, agent_storage)
    return {"message": "Company agent and all resources cleaned up"}


async def cleanup_publication_session(
    vat_number: str,
    publication_id: str,
    client: OpenAI,
    agent_storage: RedisAgentStorage,
):
    """
    Helper function to clean up resources for a specific publication.
    """
    try:
        if agent_storage.publication_exists(vat_number, publication_id):
            assistant_id = agent_storage.get_company_assistant_id(vat_number)
            publication_data = agent_storage.get_publication_data(
                vat_number, publication_id
            )

            if not assistant_id or not publication_data:
                return

            # Update the assistant to remove the vector store
            client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": []}},
            )

            # Delete the vector store
            if "vector_store_id" in publication_data:
                client.beta.vector_stores.delete(
                    vector_store_id=publication_data["vector_store_id"]
                )

            # Remove the publication from Redis
            agent_storage.delete_publication_data(vat_number, publication_id)

    except Exception as e:
        logging.error(f"Error cleaning up publication session: {e}")
        raise


async def cleanup_company_agent(
    vat_number: str,
    client: OpenAI,
    agent_storage: RedisAgentStorage,
):
    """
    Helper function to clean up all resources for a company.
    """
    try:
        if agent_storage.company_exists(vat_number):
            assistant_id = agent_storage.get_company_assistant_id(vat_number)

            # Clean up each active publication
            for publication_id in agent_storage.get_active_publications(vat_number):
                await cleanup_publication_session(
                    vat_number, publication_id, client, agent_storage
                )

            # Delete the assistant
            client.beta.assistants.delete(assistant_id=assistant_id)

            # Remove the company from Redis
            agent_storage.delete_company_data(vat_number)

    except Exception as e:
        logging.error(f"Error cleaning up company agent: {e}")
        raise
