import json
import logging
from typing import Any, List, Optional

import httpx
from fastapi import (APIRouter, Depends, HTTPException, WebSocket,
                     WebSocketDisconnect, status)
from fastapi.security import HTTPAuthorizationCredentials
from openai import OpenAI
from pydantic import BaseModel
from redis.client import Redis

import app.crud.company as crud_company
from app.ai.openai import get_openai_client
from app.config.postgres import get_session
from app.config.redis_manager import get_redis_client
from app.config.settings import Settings
from app.crud.agent import RedisAgentStorage
from app.models.company_models import Company
from app.util.clerk import AuthUser, get_auth_user
from app.util.pubproc import get_publication_workspace_documents

conversations_router = APIRouter()

settings = Settings()


class ConversationRequest(BaseModel):
    publication_workspace_id: str
    vat_number: str
    message: str
    thread_id: Optional[str] = None


class ConversationResponse(BaseModel):
    thread_id: str
    response: str
    citations: List[str]


# WebSocket message types
class WSMessageType:
    CONNECT = "connect"
    ERROR = "error"
    MESSAGE = "message"
    RESPONSE_CHUNK = "response_chunk"
    RESPONSE_COMPLETE = "response_complete"
    CITATIONS = "citations"


# Dependency to get Redis agent storage
def get_agent_storage(redis: Redis = Depends(get_redis_client)):
    return RedisAgentStorage(redis)


@conversations_router.websocket("/ws/conversation")
async def websocket_conversation(
    websocket: WebSocket,
    client: OpenAI = Depends(get_openai_client),
    agent_storage: RedisAgentStorage = Depends(get_agent_storage),
):
    await websocket.accept()

    try:
        # Wait for initial connection message with conversation params
        data = await websocket.receive_text()
        request_data = json.loads(data)

        # Validate initial message type
        if request_data.get("type") != WSMessageType.CONNECT:
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {"detail": "First message must be a connection request"},
                }
            )
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # Extract connection parameters
        params = request_data.get("data", {})
        publication_workspace_id = params.get("publication_workspace_id")
        thread_id = params.get("thread_id")
        auth_token = params.get("token")

        # Validate required parameters
        if not publication_workspace_id:
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {
                        "detail": "Missing required parameter: publication_workspace_id"
                    },
                }
            )
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # Validate auth token
        if not auth_token:
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {"detail": "Authentication token is required"},
                }
            )
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # Authenticate user with token
        try:
            # Create credentials object for auth_user function
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=auth_token
            )

            # Use the existing get_auth_user function to validate the token and get the user
            auth_user = await get_auth_user(credentials)

            if not auth_user or not auth_user.email:
                await websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": {
                            "detail": "Invalid authentication token or user email not available"
                        },
                    }
                )
                await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                return

            # Use the email from the authenticated user
            email = auth_user.email

            # Get company from the authenticated user's email
            with get_session() as session:
                company = crud_company.get_company_by_email(
                    email=email, session=session
                )

                if not company:
                    await websocket.send_json(
                        {
                            "type": WSMessageType.ERROR,
                            "data": {
                                "detail": "Company not found for authenticated user"
                            },
                        }
                    )
                    await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                    return

                # Get the VAT number from the user's company
                vat_number = company.vat_number

        except Exception as e:
            logging.error(f"Authentication error: {str(e)}")
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {"detail": f"Authentication failed: {str(e)}"},
                }
            )
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # Process WebSocket messages
        async for message in process_websocket_conversation(
            websocket,
            vat_number,
            publication_workspace_id,
            thread_id,
            company,
            client,
            agent_storage,
        ):
            pass  # The generator handles sending messages

    except WebSocketDisconnect:
        logging.info(f"WebSocket client disconnected")
    except Exception as e:
        logging.error(f"Error in WebSocket conversation: {e}")
        await websocket.send_json(
            {"type": WSMessageType.ERROR, "data": {"detail": str(e)}}
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


async def process_websocket_conversation(
    websocket: WebSocket,
    vat_number: str,
    publication_workspace_id: str,
    thread_id: Optional[str],
    company: Company,
    client: OpenAI,
    agent_storage: RedisAgentStorage,
):
    """
    Process the WebSocket conversation, handling setup and streaming responses.
    Implemented as a generator to maintain the WebSocket context.
    """

    # Check if we already have an active agent for this company
    assistant_id = agent_storage.get_company_assistant_id(vat_number)

    if not assistant_id:
        # Create a new assistant for this company
        assistant = client.beta.assistants.create(
            name=f"Company Assistant {company.name}",
            instructions=f"You are an assistant for {company.name}. Help with procurement files analysis.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
        )

        # Store the assistant ID in Redis
        agent_storage.store_company_assistant(vat_number, assistant.id)
        assistant_id = assistant.id

    # Check if we're starting a new conversation for this publication and there's already data
    if not thread_id and agent_storage.publication_exists(
        vat_number, publication_workspace_id
    ):
        # Clean up the old session if starting a new conversation
        await cleanup_publication_session(
            vat_number,
            publication_workspace_id,
            client,
            agent_storage,
        )
        # Delete immediately to prevent conflicts
        agent_storage.delete_publication_data(vat_number, publication_workspace_id)

    # Setup the conversation
    vector_store_id = None

    # If no thread_id is provided or the publication isn't active, create a new session
    if not thread_id or not agent_storage.publication_exists(
        vat_number, publication_workspace_id
    ):
        # Send status message
        await websocket.send_json(
            {
                "type": WSMessageType.RESPONSE_CHUNK,
                "data": {"content": "Setting up conversation...", "done": False},
            }
        )

        # Fetch documents for this publication
        async with httpx.AsyncClient() as http_client:
            filesmap = await get_publication_workspace_documents(
                http_client, publication_workspace_id
            )

        # Create a new vector store
        vector_store = client.beta.vector_stores.create(
            name=f"company_{vat_number}_publication_{publication_workspace_id}"
        )
        vector_store_id = vector_store.id

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
                logging.error(f"Failed to upload files to vector store: {file_batch}")
                await websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": {"detail": "Failed to process files"},
                    }
                )
                await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
                return
            if file_batch.status == "in_progress":
                # This is a simplified approach - in production, implement proper polling
                await websocket.send_json(
                    {
                        "type": WSMessageType.RESPONSE_CHUNK,
                        "data": {"content": "Processing files...", "done": False},
                    }
                )
                continue

        # Update the assistant with the new vector store
        client.beta.assistants.update(
            assistant_id=assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
        )

        # Create a new thread (without any messages yet)
        thread = client.beta.threads.create()
        thread_id = thread.id

        # Store the session information in Redis
        agent_storage.store_publication_data(
            vat_number, publication_workspace_id, vector_store.id, thread_id
        )

        await websocket.send_json(
            {
                "type": WSMessageType.RESPONSE_CHUNK,
                "data": {
                    "content": "Setup complete, ready for messages.",
                    "done": False,
                },
            }
        )
    else:
        # Continue an existing conversation
        publication_data = agent_storage.get_publication_data(
            vat_number, publication_workspace_id
        )

        # If thread_id is provided, verify it matches what we have stored
        if thread_id and publication_data.get("thread_id") != thread_id:
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {
                        "detail": "Thread not found for this publication and company"
                    },
                }
            )
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # Use the thread_id from storage if not provided
        if not thread_id:
            thread_id = publication_data.get("thread_id")

        # Get vector store ID from the publication data
        vector_store_id = publication_data.get("vector_store_id")

        # Refresh TTL for this company and publication
        agent_storage.refresh_ttl(vat_number, publication_workspace_id)

    # Main message loop
    while True:
        try:
            # Wait for message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Check message type
            if message_data.get("type") != WSMessageType.MESSAGE:
                await websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": {"detail": "Expected message type"},
                    }
                )
                continue

            # Extract the user message
            user_message = message_data.get("data", {}).get("content", "")
            if not user_message:
                await websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": {"detail": "Message cannot be empty"},
                    }
                )
                continue

            # Add the message to the thread
            client.beta.threads.messages.create(
                thread_id=thread_id, role="user", content=user_message
            )

            # Create a run with streaming
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
            )

            # Stream the response in chunks
            full_response = ""
            citations = []

            while True:
                # Get the run status
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=run.id
                )

                if run_status.status == "completed":
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

                    # Process citations and annotations
                    response_with_citations = message_content.value
                    for index, annotation in enumerate(annotations):
                        response_with_citations = response_with_citations.replace(
                            annotation.text, f"[{index}]"
                        )
                        if file_citation := getattr(annotation, "file_citation", None):
                            cited_file = client.files.retrieve(file_citation.file_id)
                            citations.append(f"[{index}] {cited_file.filename}")

                    # Send the final message with all citations properly formatted
                    await websocket.send_json(
                        {
                            "type": WSMessageType.RESPONSE_COMPLETE,
                            "data": {
                                "thread_id": thread_id,
                                "content": response_with_citations,
                                "done": True,
                            },
                        }
                    )

                    # Send citation information
                    if citations:
                        await websocket.send_json(
                            {
                                "type": WSMessageType.CITATIONS,
                                "data": {"citations": citations},
                            }
                        )

                    break

                elif run_status.status == "failed":
                    await websocket.send_json(
                        {
                            "type": WSMessageType.ERROR,
                            "data": {"detail": f"Run failed: {run_status.last_error}"},
                        }
                    )
                    break

                elif run_status.status in ["queued", "in_progress", "requires_action"]:
                    # For simplicity, just send periodic updates
                    # In a production app, you'd use the proper OpenAI streaming
                    await websocket.send_json(
                        {
                            "type": WSMessageType.RESPONSE_CHUNK,
                            "data": {"content": "Thinking...", "done": False},
                        }
                    )

                    # If requires_action, handle tool calls
                    if run_status.status == "requires_action":
                        # TODO: Handle tool calls properly
                        # This would require implementing the tool call handling logic
                        pass

                    # Yield to allow the WebSocket connection to breathe
                    yield

                    # Continue checking the status
                    continue

            yield  # Yield to maintain WebSocket context

        except WebSocketDisconnect:
            logging.info(f"WebSocket client disconnected")
            break
        except json.JSONDecodeError:
            await websocket.send_json(
                {"type": WSMessageType.ERROR, "data": {"detail": "Invalid JSON format"}}
            )
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            await websocket.send_json(
                {"type": WSMessageType.ERROR, "data": {"detail": str(e)}}
            )


@conversations_router.delete(
    "/conversation/{publication_workspace_id}", status_code=200
)
async def end_conversation(
    publication_workspace_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
    client: OpenAI = Depends(get_openai_client),
    agent_storage: RedisAgentStorage = Depends(get_agent_storage),
):
    """
    End a conversation and clean up resources for a specific publication and company.
    Requires authentication.
    """
    # Get the user's company
    with get_session() as session:
        if not auth_user.email:
            raise HTTPException(status_code=400, detail="User email not available")

        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )

        if not company:
            raise HTTPException(
                status_code=404, detail="Company not found for authenticated user"
            )

        # Get the VAT number from the user's company
        vat_number = company.vat_number

    # Check if the conversation exists
    if not agent_storage.publication_exists(vat_number, publication_workspace_id):
        raise HTTPException(
            status_code=404,
            detail="No active conversation for this publication and company",
        )

    await cleanup_publication_session(
        vat_number, publication_workspace_id, client, agent_storage
    )
    return {"message": "Conversation ended and resources cleaned up"}


@conversations_router.delete("/conversation/company", status_code=200)
async def cleanup_company(
    auth_user: AuthUser = Depends(get_auth_user),
    client: OpenAI = Depends(get_openai_client),
    agent_storage: RedisAgentStorage = Depends(get_agent_storage),
):
    """
    Clean up all resources for the authenticated user's company.
    Requires authentication.
    """
    # Get the user's company
    with get_session() as session:
        if not auth_user.email:
            raise HTTPException(status_code=400, detail="User email not available")

        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )

        if not company:
            raise HTTPException(
                status_code=404, detail="Company not found for authenticated user"
            )

        # Get the VAT number from the user's company
        vat_number = company.vat_number

    if not agent_storage.company_exists(vat_number):
        raise HTTPException(status_code=404, detail="No active agent for this company")

    await cleanup_company_agent(vat_number, client, agent_storage)
    return {"message": "Company agent and all resources cleaned up"}


async def cleanup_publication_session(
    vat_number: str,
    publication_workspace_id: str,
    client: OpenAI,
    agent_storage: RedisAgentStorage,
):
    """
    Helper function to clean up resources for a specific publication.
    """
    try:
        if agent_storage.publication_exists(vat_number, publication_workspace_id):
            assistant_id = agent_storage.get_company_assistant_id(vat_number)
            publication_data = agent_storage.get_publication_data(
                vat_number, publication_workspace_id
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
            agent_storage.delete_publication_data(vat_number, publication_workspace_id)

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
            for publication_workspace_id in agent_storage.get_active_publications(
                vat_number
            ):
                await cleanup_publication_session(
                    vat_number, publication_workspace_id, client, agent_storage
                )

            # Delete the assistant
            client.beta.assistants.delete(assistant_id=assistant_id)

            # Remove the company from Redis
            agent_storage.delete_company_data(vat_number)

    except Exception as e:
        logging.error(f"Error cleaning up company agent: {e}")
        raise
