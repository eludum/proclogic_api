import asyncio
import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI

import app.crud.company as crud_company
import app.crud.conversation as crud_conversation
import app.crud.publication as crud_publication
from app.ai.openai import get_openai_client
from app.config.postgres import get_session
from app.config.settings import Settings
from app.models.conversation_models import Conversation
from app.schemas.conversation_schemas import (
    ChatRequest,
    ChatResponse,
    ConversationSchema,
    ConversationSummary,
)
from app.util.clerk import AuthUser, get_auth_user
from app.util.conversations_helper import (
    process_ai_message,
    stream_ai_response,
    get_publication_title,
)
from app.util.converter import truncate_text

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
    connection_id = str(uuid.uuid4())[:8]  # Generate only once

    # Thread-level lock to ensure only one processing task runs at a time
    run_lock = asyncio.Lock()
    is_processing = False

    try:
        await websocket.accept()
        logging.info(f"Connection {connection_id}: Connection accepted")

        # Get initial connection data with timeout
        try:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            request_data = json.loads(data)
        except asyncio.TimeoutError:
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": "Timeout waiting for connection data"},
                }
            )
            return
        except json.JSONDecodeError:
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
            await websocket.send_json(
                {"type": "error", "data": {"detail": "Missing required parameters"}}
            )
            return

        # Authenticate user
        try:
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=auth_token
            )
            auth_user = await asyncio.wait_for(get_auth_user(credentials), timeout=5.0)

            if not auth_user or not auth_user.email:
                await websocket.send_json(
                    {"type": "error", "data": {"detail": "Invalid authentication"}}
                )
                return
        except Exception as auth_error:
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": f"Authentication failed: {str(auth_error)}"},
                }
            )
            return

        # Initialize or retrieve conversation
        try:
            with get_session() as session:
                company = crud_company.get_company_by_email(
                    email=auth_user.email, session=session
                )
                if not company:
                    await websocket.send_json(
                        {"type": "error", "data": {"detail": "Company not found"}}
                    )
                    return

                publication = crud_publication.get_publication_by_workspace_id(
                    publication_workspace_id=publication_workspace_id, session=session
                )
                if not publication:
                    await websocket.send_json(
                        {"type": "error", "data": {"detail": "Publication not found"}}
                    )
                    return

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

                # Send confirmation
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
        except Exception as db_error:
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": f"Database error: {str(db_error)}"},
                }
            )
            return

        # Keep track of conversation state
        conversation_id = conversation.id

        # Message processing loop
        while True:
            try:
                # Wait for message, with timeout
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(), timeout=300.0
                )

                try:
                    message_data = json.loads(raw_message)
                except json.JSONDecodeError:
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
                if not message_data.get("content"):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"detail": "Message missing content field"},
                        }
                    )
                    continue

                user_message = message_data.get("content")

                # Check if already processing
                if is_processing:
                    await websocket.send_json(
                        {
                            "type": "info",
                            "data": {
                                "detail": "Verwerking van je vorige bericht is nog bezig. Even geduld."
                            },
                        }
                    )
                    continue

                # Process message with lock
                try:
                    is_processing = True
                    await websocket.send_json(
                        {
                            "type": "stream_start",
                            "data": {"conversation_id": conversation_id},
                        }
                    )

                    # Save user message
                    with get_session() as session:
                        crud_conversation.add_message(
                            conversation_id=conversation_id,
                            role="user",
                            content=user_message,
                            session=session,
                        )

                        # Refresh data objects
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

                    # Process with AI
                    response_chunks = []
                    citations = []
                    ai_processing_started = False

                    # Streaming handler
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

                    # Stream response chunks
                    streaming_task = asyncio.create_task(
                        stream_with_timeout().__aiter__().__anext__()
                    )

                    while True:
                        try:
                            # Get next chunk with timeout
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

                            # Get next chunk
                            streaming_task = asyncio.create_task(
                                stream_with_timeout().__aiter__().__anext__()
                            )

                        except StopAsyncIteration:
                            # All chunks received
                            break
                        except asyncio.TimeoutError:
                            # Chunk timeout
                            if not ai_processing_started:
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "data": {
                                            "detail": "AI processing timed out without producing any response"
                                        },
                                    }
                                )
                                break
                            else:
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

                    # Process full response
                    full_response = "".join(response_chunks)
                    citations_text = "\n".join(citations) if citations else None

                    if full_response:
                        # Save to database
                        with get_session() as session:
                            crud_conversation.add_message(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=full_response,
                                citations=citations_text,
                                session=session,
                            )

                        # Send completion to client
                        await websocket.send_json(
                            {
                                "type": "stream_end",
                                "data": {
                                    "content": full_response,
                                    "citations": citations,
                                },
                            }
                        )

                except Exception as ai_error:
                    logging.error(
                        f"Connection {connection_id}: Error in AI processing: {str(ai_error)}"
                    )
                    logging.exception(ai_error)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "detail": f"Error processing response: {str(ai_error)}"
                            },
                        }
                    )

                    # Try to save error message to database
                    try:
                        with get_session() as session:
                            crud_conversation.add_message(
                                conversation_id=conversation_id,
                                role="assistant",
                                content="Sorry, er is een fout opgetreden bij het verwerken van je verzoek. Probeer het opnieuw.",
                                session=session,
                            )
                    except Exception:
                        pass

                finally:
                    # Add this line to ensure processing state is reset even on errors
                    is_processing = False

            except asyncio.TimeoutError:
                # Client inactive
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

            except Exception as e:
                logging.error(
                    f"Connection {connection_id}: Error processing message: {e}"
                )
                await websocket.send_json(
                    {"type": "error", "data": {"detail": f"Error: {str(e)}"}}
                )
                is_processing = False  # Reset state on error

    except WebSocketDisconnect:
        logging.info(f"Connection {connection_id}: Client disconnected during setup")
    except Exception as e:
        logging.error(f"Connection {connection_id}: WebSocket error: {str(e)}")
        try:
            await websocket.send_json(
                {"type": "error", "data": {"detail": f"Error: {str(e)}"}}
            )
        except:
            pass  # Can't do anything if sending fails
