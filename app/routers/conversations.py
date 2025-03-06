import asyncio
import json
import logging
import time
import uuid
from io import BytesIO
from typing import List, Optional, Tuple

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from sqlalchemy.orm import Session

import app.crud.company as crud_company
import app.crud.conversation as crud_conversation
import app.crud.publication as crud_publication
from app.ai.openai import get_openai_client
from app.config.postgres import get_session
from app.config.settings import Settings
from app.models.company_models import Company
from app.models.publication_models import Publication
from app.models.conversation_models import Conversation
from app.schemas.conversation_schemas import (
    ChatRequest,
    ChatResponse,
    ConversationSchema,
    ConversationSummary,
)
from app.util.clerk import AuthUser, get_auth_user
from app.util.converter import truncate_text
from app.util.pubproc import get_publication_workspace_documents

conversations_router = APIRouter()

security = HTTPBearer()
settings = Settings()


@conversations_router.get("/conversations/", response_model=List[ConversationSummary])
async def get_user_conversations(
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get all conversations for the authenticated user."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get all conversations for this company
        conversations = crud_conversation.get_company_conversations(
            company_vat_number=company.vat_number, session=session
        )

        # Create summary responses
        result = []
        for conv in conversations:
            # Get the last message if any exist
            last_message = None
            message_count = 0

            if conv.messages:
                sorted_messages = sorted(
                    conv.messages, key=lambda m: m.created_at, reverse=True
                )
                last_message = sorted_messages[0] if sorted_messages else None
                message_count = len(conv.messages)

            # Get publication title
            publication_title = get_publication_title(conv.publication)

            result.append(
                ConversationSummary(
                    id=conv.id,
                    publication_workspace_id=conv.publication_workspace_id,
                    publication_title=publication_title,
                    updated_at=conv.updated_at,
                    last_message_preview=(
                        truncate_text(last_message.content, 100)
                        if last_message
                        else None
                    ),
                    message_count=message_count,
                )
            )

        return result


@conversations_router.get(
    "/conversations/{conversation_id}", response_model=ConversationSchema
)
async def get_conversation(
    conversation_id: int,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get a specific conversation by ID."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        conversation = crud_conversation.get_conversation_by_id(
            conversation_id=conversation_id, session=session
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Verify ownership
        if conversation.company_vat_number != company.vat_number:
            raise HTTPException(
                status_code=403, detail="Unauthorized access to conversation"
            )

        return conversation


@conversations_router.post("/conversations/chat", response_model=ChatResponse)
async def chat_with_publication(
    request: ChatRequest,
    auth_user: AuthUser = Depends(get_auth_user),
    client: OpenAI = Depends(get_openai_client),
):
    """Send a message to a publication and get a response."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Verify publication exists
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=request.publication_workspace_id, session=session
        )
        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        # Get or create conversation
        conversation = None
        if request.conversation_id:
            conversation = crud_conversation.get_conversation_by_id(
                conversation_id=request.conversation_id, session=session
            )

            # Verify ownership
            if conversation and conversation.company_vat_number != company.vat_number:
                raise HTTPException(
                    status_code=403, detail="Unauthorized access to conversation"
                )

        if not conversation:
            conversation = crud_conversation.get_or_create_conversation(
                company_vat_number=company.vat_number,
                publication_workspace_id=request.publication_workspace_id,
                session=session,
            )

        # Add user message to conversation
        user_message = crud_conversation.add_message(
            conversation_id=conversation.id,
            role="user",
            content=request.message,
            session=session,
        )

        # Process the message with OpenAI
        response_content, citations = await process_ai_message(
            conversation=conversation,
            user_message=request.message,
            company=company,
            publication=publication,
            client=client,
        )

        # Save the AI response
        assistant_message = crud_conversation.add_message(
            conversation_id=conversation.id,
            role="assistant",
            content=response_content,
            citations=citations,
            session=session,
        )

        return ChatResponse(conversation_id=conversation.id, message=assistant_message)


@conversations_router.delete("/conversations/{conversation_id}", status_code=200)
async def delete_conversation(
    conversation_id: int,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Deactivate a conversation."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        conversation = crud_conversation.get_conversation_by_id(
            conversation_id=conversation_id, session=session
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Verify ownership
        if conversation.company_vat_number != company.vat_number:
            raise HTTPException(
                status_code=403, detail="Unauthorized access to conversation"
            )

        success = crud_conversation.deactivate_conversation(
            conversation_id=conversation_id, session=session
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete conversation")

        return {"message": "Conversation successfully deleted"}


@conversations_router.get(
    "/publications/{publication_workspace_id}/conversation",
    response_model=Optional[ConversationSchema],
)
async def get_publication_conversation(
    publication_workspace_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get the active conversation for a publication if it exists."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get all conversations for the publication and company
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.company_vat_number == company.vat_number,
                Conversation.publication_workspace_id == publication_workspace_id,
                Conversation.is_active == True,
            )
            .first()
        )

        if not conversation:
            return None

        return conversation


@conversations_router.websocket("/ws/conversation")
async def websocket_conversation(
    websocket: WebSocket,
    client: OpenAI = Depends(get_openai_client),
):
    """Enhanced WebSocket endpoint with improved error handling and logging."""
    logging.info("WebSocket connection attempt received")

    try:
        await websocket.accept()
        logging.info("WebSocket connection accepted")

        # Connection tracking
        connection_id = str(uuid.uuid4())[:8]
        logging.info(f"Connection {connection_id}: New connection established")

        # Get initial connection data with timeout
        try:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            logging.info(f"Connection {connection_id}: Initial data received")
            request_data = json.loads(data)
            logging.debug(f"Connection {connection_id}: Request data: {request_data}")
        except asyncio.TimeoutError:
            logging.error(
                f"Connection {connection_id}: Timeout waiting for initial data"
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": "Timeout waiting for connection data"},
                }
            )
            return
        except json.JSONDecodeError:
            logging.error(f"Connection {connection_id}: Invalid JSON in initial data")
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": "Invalid JSON format in connection data"},
                }
            )
            return

        # Extract connection parameters
        publication_workspace_id = request_data.get("publication_workspace_id")
        conversation_id = request_data.get("conversation_id")
        auth_token = request_data.get("token")

        if not publication_workspace_id or not auth_token:
            logging.error(f"Connection {connection_id}: Missing required parameters")
            await websocket.send_json(
                {"type": "error", "data": {"detail": "Missing required parameters"}}
            )
            return

        # Log connection parameters (without the full token for security)
        logging.info(
            f"Connection {connection_id}: Parameters received - "
            f"publication_id: {publication_workspace_id}, "
            f"conversation_id: {conversation_id}"
        )

        # Authenticate user with timeout
        try:
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=auth_token
            )
            auth_user = await asyncio.wait_for(get_auth_user(credentials), timeout=5.0)

            if not auth_user or not auth_user.email:
                logging.error(f"Connection {connection_id}: Invalid authentication")
                await websocket.send_json(
                    {"type": "error", "data": {"detail": "Invalid authentication"}}
                )
                return

            logging.info(
                f"Connection {connection_id}: User authenticated successfully: {auth_user.email}"
            )

        except asyncio.TimeoutError:
            logging.error(f"Connection {connection_id}: Authentication timed out")
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": "Authentication request timed out"},
                }
            )
            return
        except Exception as auth_error:
            logging.error(
                f"Connection {connection_id}: Authentication error: {str(auth_error)}"
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": f"Authentication failed: {str(auth_error)}"},
                }
            )
            return

        # Get company and publication with timeout and session management
        try:
            with get_session() as session:
                # Get company
                company = crud_company.get_company_by_email(
                    email=auth_user.email, session=session
                )
                if not company:
                    logging.error(
                        f"Connection {connection_id}: Company not found for email {auth_user.email}"
                    )
                    await websocket.send_json(
                        {"type": "error", "data": {"detail": "Company not found"}}
                    )
                    return
                logging.info(
                    f"Connection {connection_id}: Found company: {company.name}"
                )

                # Get publication
                publication = crud_publication.get_publication_by_workspace_id(
                    publication_workspace_id=publication_workspace_id, session=session
                )
                if not publication:
                    logging.error(
                        f"Connection {connection_id}: Publication not found: {publication_workspace_id}"
                    )
                    await websocket.send_json(
                        {"type": "error", "data": {"detail": "Publication not found"}}
                    )
                    return
                logging.info(
                    f"Connection {connection_id}: Found publication: {publication_workspace_id}"
                )

                # Get or create conversation
                conversation = None
                if conversation_id:
                    conversation = crud_conversation.get_conversation_by_id(
                        conversation_id=conversation_id, session=session
                    )

                    # Verify ownership
                    if (
                        conversation
                        and conversation.company_vat_number != company.vat_number
                    ):
                        logging.error(
                            f"Connection {connection_id}: Unauthorized access to conversation"
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "data": {
                                    "detail": "Unauthorized access to conversation"
                                },
                            }
                        )
                        return

                if not conversation:
                    conversation = crud_conversation.get_or_create_conversation(
                        company_vat_number=company.vat_number,
                        publication_workspace_id=publication_workspace_id,
                        session=session,
                    )
                    logging.info(
                        f"Connection {connection_id}: Created new conversation: {conversation.id}"
                    )
                else:
                    logging.info(
                        f"Connection {connection_id}: Using existing conversation: {conversation.id}"
                    )

                # Send confirmation to client
                pub_title = get_publication_title(publication)
                await websocket.send_json(
                    {
                        "type": "connected",
                        "data": {
                            "conversation_id": conversation.id,
                            "company_name": company.name,
                            "publication_title": pub_title,
                        },
                    }
                )
                logging.info(
                    f"Connection {connection_id}: Sent connection confirmation"
                )

        except Exception as db_error:
            logging.error(
                f"Connection {connection_id}: Database error: {str(db_error)}"
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": f"Database error: {str(db_error)}"},
                }
            )
            return

        # Keep track of connection state
        conversation_id = conversation.id

        # Start listening for messages
        while True:
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(), timeout=300.0
                )  # 5-minute timeout
                logging.info(f"Connection {connection_id}: Received message")

                try:
                    message_data = json.loads(raw_message)
                    logging.debug(
                        f"Connection {connection_id}: Parsed message: {message_data}"
                    )
                except json.JSONDecodeError as json_err:
                    logging.error(
                        f"Connection {connection_id}: JSON decode error: {json_err}"
                    )
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "detail": "Invalid message format, expecting JSON"
                            },
                        }
                    )
                    continue

                # Extract user message
                user_message = ""
                if message_data.get("content"):
                    user_message = message_data.get("content")
                else:
                    logging.warning(
                        f"Connection {connection_id}: Missing content in message"
                    )
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"detail": "Message missing content field"},
                        }
                    )
                    continue

                # Start stream response
                await websocket.send_json(
                    {
                        "type": "stream_start",
                        "data": {"conversation_id": conversation_id},
                    }
                )
                logging.info(f"Connection {connection_id}: Stream started for message")

                # Process in new session since WebSocket connection is long-lived
                with get_session() as session:
                    # Add user message to database
                    crud_conversation.add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=user_message,
                        session=session,
                    )
                    logging.info(
                        f"Connection {connection_id}: Saved user message to database"
                    )

                    # Get fresh data
                    company_refresh = crud_company.get_company_by_email(
                        email=auth_user.email, session=session
                    )
                    publication_refresh = (
                        crud_publication.get_publication_by_workspace_id(
                            publication_workspace_id=publication_workspace_id,
                            session=session,
                        )
                    )
                    conversation_refresh = crud_conversation.get_conversation_by_id(
                        conversation_id=conversation_id, session=session
                    )
                    logging.info(
                        f"Connection {connection_id}: Refreshed database objects"
                    )

                # Process with AI and stream response - with timeout protection
                response_chunks = []
                citations = []
                ai_processing_started = False

                try:
                    # Stream the AI response with a timeout wrapper
                    async def stream_with_timeout():
                        nonlocal ai_processing_started
                        async for chunk, citation in stream_ai_response(
                            conversation=conversation_refresh,
                            user_message=user_message,
                            company=company_refresh,
                            publication=publication_refresh,
                            client=client,
                        ):
                            ai_processing_started = True
                            yield chunk, citation

                    # Use a timeout for the entire streaming process
                    streaming_task = asyncio.create_task(
                        stream_with_timeout().__aiter__().__anext__()
                    )

                    while True:
                        try:
                            # 60-second timeout for each chunk
                            chunk, citation = await asyncio.wait_for(
                                streaming_task, timeout=60.0
                            )
                            response_chunks.append(chunk)
                            if citation:
                                citations.extend(citation)

                            # Send chunk to client
                            await websocket.send_json(
                                {"type": "stream_chunk", "data": {"content": chunk}}
                            )
                            logging.debug(
                                f"Connection {connection_id}: Sent chunk of size {len(chunk)}"
                            )

                            # Start next chunk
                            streaming_task = asyncio.create_task(
                                stream_with_timeout().__aiter__().__anext__()
                            )

                            # Small delay to prevent flooding
                            await asyncio.sleep(0.01)
                        except StopAsyncIteration:
                            # All chunks have been processed
                            logging.info(
                                f"Connection {connection_id}: AI stream completed normally"
                            )
                            break
                        except asyncio.TimeoutError:
                            # Chunk timeout - stop processing but handle what we've got
                            logging.warning(
                                f"Connection {connection_id}: Timeout waiting for AI response chunk"
                            )
                            if not ai_processing_started:
                                # If we haven't received anything yet, this is a fatal error
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {
                                            "detail": "AI processing timed out without producing any response"
                                        },
                                    }
                                )
                                # Don't save an empty message
                                break
                            else:
                                # We got partial results - warn but continue with what we have
                                await websocket.send_json(
                                    {
                                        "type": "stream_chunk",
                                        "data": {
                                            "content": " [Response truncated due to processing timeout]"
                                        },
                                    }
                                )
                                response_chunks.append(
                                    " [Response truncated due to processing timeout]"
                                )
                                break

                    # Combine all chunks
                    full_response = "".join(response_chunks)
                    citations_text = "\n".join(citations) if citations else None

                    if full_response:  # Only save if we have something to save
                        # Save the full response in database
                        with get_session() as session:
                            crud_conversation.add_message(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=full_response,
                                citations=citations_text,
                                session=session,
                            )
                            logging.info(
                                f"Connection {connection_id}: Saved AI response to database"
                            )

                        # Send complete message
                        await websocket.send_json(
                            {
                                "type": "stream_end",
                                "data": {
                                    "content": full_response,
                                    "citations": citations,
                                },
                            }
                        )
                        logging.info(
                            f"Connection {connection_id}: Sent stream_end with response of size {len(full_response)}"
                        )

                except Exception as ai_error:
                    logging.error(
                        f"Connection {connection_id}: Error in AI processing: {str(ai_error)}"
                    )
                    logging.exception(ai_error)  # Log the full exception with traceback
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "detail": f"Error processing response: {str(ai_error)}"
                            },
                        }
                    )

                    # Try to save an error message if we have a connection ID
                    if conversation_id:
                        try:
                            with get_session() as session:
                                crud_conversation.add_message(
                                    conversation_id=conversation_id,
                                    role="assistant",
                                    content="Sorry, an error occurred while processing your request. Please try again.",
                                    session=session,
                                )
                        except Exception as save_error:
                            logging.error(
                                f"Connection {connection_id}: Failed to save error message: {str(save_error)}"
                            )

            except asyncio.TimeoutError:
                # Client hasn't sent a message for a long time
                logging.info(
                    f"Connection {connection_id}: Session timed out waiting for client message"
                )
                await websocket.send_json(
                    {
                        "type": "timeout",
                        "data": {"detail": "Session timed out due to inactivity"},
                    }
                )
                break
            except WebSocketDisconnect:
                logging.info(f"Connection {connection_id}: Client disconnected")
                break
            except json.JSONDecodeError as e:
                logging.error(
                    f"Connection {connection_id}: Error decoding message: {e}"
                )
                await websocket.send_json(
                    {"type": "error", "data": {"detail": "Invalid message format"}}
                )
            except Exception as e:
                logging.error(
                    f"Connection {connection_id}: Error processing message: {e}"
                )
                logging.exception(e)  # Log the full exception with traceback
                await websocket.send_json(
                    {"type": "error", "data": {"detail": f"Error: {str(e)}"}}
                )

    except WebSocketDisconnect:
        logging.info(f"WebSocket client disconnected during setup")
    except Exception as e:
        logging.error(f"WebSocket error during setup: {str(e)}")
        logging.exception(e)
        try:
            await websocket.send_json(
                {"type": "error", "data": {"detail": f"Error: {str(e)}"}}
            )
        except:
            pass  # We can't do anything if sending the error itself fails


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

        # Update conversation with assistant ID
        with get_session() as session:
            crud_conversation.update_conversation_ai_info(
                conversation_id=conversation.id,
                assistant_id=assistant_id,
                thread_id=thread_id,
                session=session,
            )

    # Add message to thread ONLY ONCE before creating the run
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

    try:
        # First yield an initial placeholder to start the stream
        yield "Denken...", []

        # Poll until the run is completed
        completed = False
        while not completed:
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

                if messages and messages[0].content and messages[0].content[0].text:
                    message_content = messages[0].content[0].text
                    response_text = message_content.value

                    # Process citations
                    annotations = message_content.annotations
                    for index, annotation in enumerate(annotations):
                        if file_citation := getattr(annotation, "file_citation", None):
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
                        "Stream AI: No message content found after completion"
                    )
                    yield "Sorry, I couldn't generate a response.", []

            elif status == "failed":
                error_message = "An error occurred"
                if hasattr(run_status, "last_error") and run_status.last_error:
                    error_message = run_status.last_error.message
                logging.error(f"Stream AI: Run failed: {error_message}")
                yield f"Sorry, an error occurred: {error_message}", []
                break

            elif status == "cancelled":
                logging.info("Stream AI: Run was cancelled")
                yield "The operation was cancelled.", []
                break

            elif status == "expired":
                logging.info("Stream AI: Run expired")
                yield "The operation timed out.", []
                break

    except Exception as e:
        logging.error(f"Stream AI: Error in streaming: {e}")
        yield f"Sorry, an unexpected error occurred: {str(e)}", []


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
