import json
import logging
from typing import List, Optional

import httpx
import asyncio
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from pydantic import BaseModel
from redis.client import Redis

import app.crud.company as crud_company
from app.ai.openai import get_openai_client
from app.config.postgres import get_session
from app.config.redis_manager import get_redis_client
from app.config.settings import Settings
from app.models.company_models import Company
from app.util.clerk import AuthUser, get_auth_user
from app.util.pubproc import get_publication_workspace_documents
from app.util.redis_cache import get_thread_id, store_thread_id, refresh_thread_ttl

conversations_router = APIRouter()

settings = Settings()
security = HTTPBearer()


# WebSocket message types
class WSMessageType:
    CONNECT = "connect"
    ERROR = "error"
    MESSAGE = "message"
    RESPONSE_CHUNK = "response_chunk"
    RESPONSE_COMPLETE = "response_complete"
    CITATIONS = "citations"


# Models for request/response
class ConversationRequest(BaseModel):
    publication_workspace_id: str
    message: str
    thread_id: Optional[str] = None


class ConversationResponse(BaseModel):
    thread_id: str
    response: str
    citations: List[str]


# Helper function to get Redis client
def get_redis() -> Redis:
    return get_redis_client()


@conversations_router.websocket("/ws/conversation")
async def websocket_conversation(
    websocket: WebSocket,
    client: OpenAI = Depends(get_openai_client),
    redis: Redis = Depends(get_redis),
):
    await websocket.accept()

    try:
        # Wait for initial connection message with conversation params
        data = await websocket.receive_text()
        
        try:
            request_data = json.loads(data)
        except json.JSONDecodeError:
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {"detail": "Invalid JSON format in connection request"},
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

            # Get company from the authenticated user's email
            with get_session() as session:
                company = crud_company.get_company_by_email(
                    email=auth_user.email, session=session
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

        # Process conversation
        conversation_handler = ConversationHandler(
            websocket=websocket,
            company=company,
            vat_number=vat_number,
            publication_workspace_id=publication_workspace_id,
            thread_id=thread_id,
            client=client,
            redis=redis,
        )

        await conversation_handler.process()

    except WebSocketDisconnect:
        logging.info("WebSocket client disconnected")
    except Exception as e:
        logging.error(f"Error in WebSocket conversation: {e}")
        await websocket.send_json(
            {"type": WSMessageType.ERROR, "data": {"detail": str(e)}}
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


class ConversationHandler:
    """Handles the conversation flow and state for a WebSocket connection"""

    def __init__(
        self,
        websocket: WebSocket,
        company: Company,
        vat_number: str,
        publication_workspace_id: str,
        thread_id: Optional[str],
        client: OpenAI,
        redis: Redis,
    ):
        self.websocket = websocket
        self.company = company
        self.vat_number = vat_number
        self.publication_workspace_id = publication_workspace_id
        self.thread_id = thread_id
        self.client = client
        self.redis = redis
        self.assistant_id = None
        self.vector_store_id = None

    async def process(self):
        """Main processing method for the conversation handler"""
        # Set up the conversation
        await self.setup_conversation()

        # Process messages
        await self.process_messages()

async def setup_conversation(self):
    """Set up the conversation by creating or retrieving the assistant and thread"""
    # First, check if we have a thread ID in Redis
    if not self.thread_id:
        try:
            existing_thread_id = get_thread_id(
                self.redis, self.vat_number, self.publication_workspace_id
            )
            if existing_thread_id:
                self.thread_id = existing_thread_id
                logging.info(f"Retrieved thread ID from Redis: {self.thread_id}")

                # Send status to client
                await self.websocket.send_json(
                    {
                        "type": WSMessageType.RESPONSE_CHUNK,
                        "data": {
                            "content": "Continuing previous conversation...",
                            "done": False,
                        },
                    }
                )

                # Refresh TTL
                refresh_thread_ttl(
                    self.redis, self.vat_number, self.publication_workspace_id
                )
        except Exception as e:
            logging.warning(f"Error retrieving thread ID: {str(e)}")
            # Continue without the thread ID - we'll create a new one

    async def setup_assistant(self) -> str:
        """Set up the assistant with vector store for file search"""
        # Check if company already has an assistant
        company_name = self.company.name
        assistants = self.client.beta.assistants.list(
            order="desc",
            limit=100,
        )

        # Look for an existing assistant for this company
        assistant_id = None
        for assistant in assistants.data:
            if assistant.name == f"Company Assistant {company_name}":
                assistant_id = assistant.id
                break

        if not assistant_id:
            # Create a new assistant for this company
            assistant = self.client.beta.assistants.create(
                name=f"Company Assistant {company_name}",
                instructions=f"You are an assistant for {company_name}. Help with procurement files analysis.",
                model="gpt-4o-mini",
                tools=[{"type": "file_search"}],
            )
            assistant_id = assistant.id

        # Fetch documents for this publication
        async with httpx.AsyncClient() as http_client:
            filesmap = await get_publication_workspace_documents(
                http_client, self.publication_workspace_id
            )

        if filesmap:
            # Create a vector store for these files
            vector_store = self.client.beta.vector_stores.create(
                name=f"publication_{self.publication_workspace_id}"
            )
            self.vector_store_id = vector_store.id

            # Filter files with accepted extensions
            filtered_filesmap = {
                file_name: file_data
                for file_name, file_data in filesmap.items()
                if file_name.lower().endswith(
                    tuple(settings.openai_vector_store_accepted_formats)
                )
            }

            if filtered_filesmap:
                # Upload files to vector store
                file_batch = (
                    self.client.beta.vector_stores.file_batches.upload_and_poll(
                        vector_store_id=vector_store.id,
                        files=list(filtered_filesmap.values()),
                    )
                )

                if file_batch.status != "completed":
                    logging.error(f"Failed to upload files: {file_batch.status}")
                    await self.websocket.send_json(
                        {
                            "type": WSMessageType.ERROR,
                            "data": {"detail": "Failed to process files"},
                        }
                    )
                    raise HTTPException(
                        status_code=500, detail="Failed to process files"
                    )

                # Update assistant with vector store
                self.client.beta.assistants.update(
                    assistant_id=assistant_id,
                    tool_resources={
                        "file_search": {"vector_store_ids": [vector_store.id]}
                    },
                )
            else:
                # Update assistant with empty vector store
                self.client.beta.assistants.update(
                    assistant_id=assistant_id,
                    tool_resources={"file_search": {"vector_store_ids": []}},
                )
        else:
            # Update assistant with empty vector store
            self.client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": []}},
            )

        return assistant_id

    async def process_messages(self):
        """Process messages from the client and send responses"""
        while True:
            try:
                # Wait for message from client
                data = await self.websocket.receive_text()
                message_data = json.loads(data)

                # Check message type
                if message_data.get("type") != WSMessageType.MESSAGE:
                    await self.websocket.send_json(
                        {
                            "type": WSMessageType.ERROR,
                            "data": {"detail": "Expected message type"},
                        }
                    )
                    continue

                # Extract the user message
                user_message = message_data.get("data", {}).get("content", "")
                if not user_message:
                    await self.websocket.send_json(
                        {
                            "type": WSMessageType.ERROR,
                            "data": {"detail": "Message cannot be empty"},
                        }
                    )
                    continue

                # Add the message to the thread
                self.client.beta.threads.messages.create(
                    thread_id=self.thread_id, role="user", content=user_message
                )

                # Create a run
                run = self.client.beta.threads.runs.create(
                    thread_id=self.thread_id,
                    assistant_id=self.assistant_id,
                )

                # Process the run
                await self.process_run(run.id)

                # Refresh the thread TTL
                refresh_thread_ttl(
                    self.redis, self.vat_number, self.publication_workspace_id
                )

            except WebSocketDisconnect:
                logging.info(f"WebSocket client disconnected")
                break
            except json.JSONDecodeError:
                await self.websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": {"detail": "Invalid JSON format"},
                    }
                )
            except Exception as e:
                logging.error(f"Error processing message: {e}")
                await self.websocket.send_json(
                    {"type": WSMessageType.ERROR, "data": {"detail": str(e)}}
                )

    async def process_run(self, run_id: str):
        """Process a run and stream the results"""
        citations = []

        while True:
            # Get the run status
            run_status = self.client.beta.threads.runs.retrieve(
                thread_id=self.thread_id, run_id=run_id
            )

            if run_status.status == "completed":
                # Get the assistant's response messages
                messages = list(
                    self.client.beta.threads.messages.list(
                        thread_id=self.thread_id,
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
                        cited_file = self.client.files.retrieve(file_citation.file_id)
                        citations.append(f"[{index}] {cited_file.filename}")

                # Send the final message with all citations properly formatted
                await self.websocket.send_json(
                    {
                        "type": WSMessageType.RESPONSE_COMPLETE,
                        "data": {
                            "thread_id": self.thread_id,
                            "content": response_with_citations,
                            "done": True,
                        },
                    }
                )

                # Send citation information
                if citations:
                    await self.websocket.send_json(
                        {
                            "type": WSMessageType.CITATIONS,
                            "data": {"citations": citations},
                        }
                    )

                break

            elif run_status.status == "failed":
                await self.websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": {"detail": f"Run failed: {run_status.last_error}"},
                    }
                )
                break

            elif run_status.status in ["queued", "in_progress", "requires_action"]:
                # Send periodic updates
                await self.websocket.send_json(
                    {
                        "type": WSMessageType.RESPONSE_CHUNK,
                        "data": {"content": "Thinking...", "done": False},
                    }
                )

                # If requires_action, handle tool calls
                if run_status.status == "requires_action":
                    # Handle tool calls if needed
                    pass

                # Small delay before checking again
                await asyncio.sleep(1)


@conversations_router.delete(
    "/conversation/{publication_workspace_id}", status_code=200
)
async def end_conversation(
    publication_workspace_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
    client: OpenAI = Depends(get_openai_client),
    redis: Redis = Depends(get_redis),
):
    """End a conversation and clean up resources for a specific publication and company"""
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

        vat_number = company.vat_number

    # Get thread_id from Redis
    thread_id = get_thread_id(redis, vat_number, publication_workspace_id)
    if not thread_id:
        raise HTTPException(status_code=404, detail="No active conversation found")

    # Clean up vector store if needed
    try:
        # Delete the thread from Redis
        redis.delete(f"thread:{vat_number}:{publication_workspace_id}")

        return {"message": "Conversation ended and resources cleaned up"}
    except Exception as e:
        logging.error(f"Error cleaning up conversation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error cleaning up conversation: {str(e)}"
        )
