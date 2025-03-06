import asyncio
import json
import logging
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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
    MessageSchema,
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
    await websocket.accept()
    logging.info("WebSocket connection accepted")

    try:
        # Get initial connection data
        data = await websocket.receive_text()
        request_data = json.loads(data)

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
            auth_user = await get_auth_user(credentials)

            if not auth_user or not auth_user.email:
                await websocket.send_json(
                    {"type": "error", "data": {"detail": "Invalid authentication"}}
                )
                return

        except Exception as auth_error:
            logging.error(f"Authentication error: {str(auth_error)}")
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {"detail": f"Authentication failed: {str(auth_error)}"},
                }
            )
            return

        # Get company and publication
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
                            "data": {"detail": "Unauthorized access to conversation"},
                        }
                    )
                    return

            if not conversation:
                conversation = crud_conversation.get_or_create_conversation(
                    company_vat_number=company.vat_number,
                    publication_workspace_id=publication_workspace_id,
                    session=session,
                )

            # Send conversation ID to client
            await websocket.send_json(
                {
                    "type": "connected",
                    "data": {
                        "conversation_id": conversation.id,
                        "company_name": company.name,
                        "publication_title": get_publication_title(publication),
                    },
                }
            )

        # Start listening for messages
        while True:
            try:
                message_data = json.loads(await websocket.receive_text())

                if message_data.get("type") != "message":
                    continue

                user_message = message_data.get("content", "")
                if not user_message:
                    continue

                # Start stream response
                await websocket.send_json(
                    {
                        "type": "stream_start",
                        "data": {"conversation_id": conversation.id},
                    }
                )

                # Process in new session since WebSocket connection is long-lived
                with get_session() as session:
                    # Add user message to database
                    crud_conversation.add_message(
                        conversation_id=conversation.id,
                        role="user",
                        content=user_message,
                        session=session,
                    )

                    # Get fresh company and publication data
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
                        conversation_id=conversation.id, session=session
                    )

                # Process with AI and stream response
                response_chunks = []
                citations = []

                # Stream the AI response
                async for chunk, citation in stream_ai_response(
                    conversation=conversation_refresh,
                    user_message=user_message,
                    company=company_refresh,
                    publication=publication_refresh,
                    client=client,
                ):
                    response_chunks.append(chunk)
                    if citation:
                        citations.extend(citation)

                    # Send chunk to client
                    await websocket.send_json(
                        {"type": "stream_chunk", "data": {"content": chunk}}
                    )

                    # Small delay to prevent flooding
                    await asyncio.sleep(0.01)

                # Combine all chunks
                full_response = "".join(response_chunks)
                citations_text = "\n".join(citations) if citations else None

                # Save the full response in database
                with get_session() as session:
                    crud_conversation.add_message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=full_response,
                        citations=citations_text,
                        session=session,
                    )

                # Send complete message
                await websocket.send_json(
                    {
                        "type": "stream_end",
                        "data": {"content": full_response, "citations": citations},
                    }
                )
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding message: {e}")
                await websocket.send_json(
                    {"type": "error", "data": {"detail": "Invalid message format"}}
                )
            except Exception as e:
                logging.error(f"Error processing message: {e}")
                await websocket.send_json(
                    {"type": "error", "data": {"detail": f"Error: {str(e)}"}}
                )

    except WebSocketDisconnect:
        logging.info("WebSocket client disconnected")
    except Exception as e:
        logging.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.send_json(
                {"type": "error", "data": {"detail": f"Error: {str(e)}"}}
            )
        except:
            pass


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
    """Stream a response from OpenAI."""
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

    # Create a run with streaming
    run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant_id
    )

    # Get run status and start streaming when available
    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id, run_id=run.id
        )

        if run_status.status == "completed":
            # Get messages
            messages = list(
                client.beta.threads.messages.list(
                    thread_id=thread_id, order="desc", limit=1
                )
            )

            if not messages:
                yield "No response was generated.", []
                return

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

            # For simulating streaming in non-streaming context, break into chunks
            for i in range(0, len(response_text), 10):
                chunk = response_text[i : i + 10]
                yield chunk, [] if i < len(response_text) - 10 else citations
                await asyncio.sleep(0.01)
            return

        elif run_status.status == "failed":
            yield "Sorry, I had trouble processing your request.", []
            return

        # Add some delay to avoid hammering the API
        await asyncio.sleep(0.5)


async def setup_assistant(
    client: OpenAI,
    company: Company,
    publication: Publication,
) -> str:
    """Set up an assistant for the conversation."""
    try:
        # First, try to find if we already have an assistant for this publication
        assistants = client.beta.assistants.list(
            order="desc",
            limit=50,
        )

        assistant_name = f"Publication Assistant {publication.publication_workspace_id}"

        # Look for existing assistant
        for assistant in assistants.data:
            if assistant.name == assistant_name:
                return assistant.id

        # Create a new assistant
        assistant = client.beta.assistants.create(
            name=assistant_name,
            instructions=f"""You are an assistant helping the company {company.name} with public procurement document analysis.
            The publication is about: {get_publication_title(publication)}
            Always respond in Dutch unless specifically asked to use another language.
            Be concise but complete in your answers. Focus on helping understand requirements, deadlines, and other important information.
            """,
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
        )

        # Try to get documents and set up vector store
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

                    # Filter files with acceptable extensions
                    filtered_files = {
                        filename: file_data
                        for filename, file_data in filesmap.items()
                        if filename.lower().endswith(
                            tuple(settings.openai_vector_store_accepted_formats)
                        )
                    }

                    if filtered_files:
                        # Prepare files for upload
                        file_objects = []
                        for filename, file_data in filtered_files.items():
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

                        if file_objects:
                            # Upload files to vector store
                            file_batch = (
                                client.beta.vector_stores.file_batches.upload_and_poll(
                                    vector_store_id=vector_store.id, files=file_objects
                                )
                            )

                            if file_batch.status == "completed":
                                # Update assistant with vector store
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

        return assistant.id

    except Exception as e:
        logging.error(f"Error setting up assistant: {e}")
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
