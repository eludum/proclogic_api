import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel

import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.ai.openai import get_openai_client
from app.config.postgres import get_session
from app.config.settings import Settings
from app.crud.mapper import convert_publication_to_out_schema_with_company
from app.schemas.publication_out_schemas import PublicationOut
from app.util.pubproc import get_publication_workspace_documents


settings = Settings()

publications_router = APIRouter()


class ConversationRequest(BaseModel):
    publication_id: str
    message: str
    thread_id: Optional[str] = None  # For continuing conversations


class ConversationResponse(BaseModel):
    thread_id: str
    response: str
    citations: List[str]


# Store active vector stores for each publication to avoid recreating them
active_sessions = {}


@publications_router.get(
    "/publications/{company_vatnumber}/", response_model=List[PublicationOut]
)
async def get_publications(company_vatnumber: str) -> List[PublicationOut]:
    with get_session() as session:
        publications = crud_publication.get_all_publications(session=session)

        company = crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        )

        return [
            convert_publication_to_out_schema_with_company(
                publication=publication, company=company
            )
            for publication in publications
        ]


@publications_router.get(
    "/publications/{company_vatnumber}/publication/{publication_workspace_id}/",
    response_model=PublicationOut,
)
async def get_publication_by_workspace_id(
    company_vatnumber: str,
    publication_workspace_id: str,
) -> PublicationOut:
    with get_session() as session:
        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        company = crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        )

        return convert_publication_to_out_schema_with_company(
            publication=publication, company=company
        )


@publications_router.get(
    "/publications/{company_vatnumber}/search/{search_term}/",
    response_model=List[PublicationOut],
)
async def search_publications(
    company_vatnumber: str,
    search_term: str,
) -> List[PublicationOut]:
    with get_session() as session:
        publications = crud_publication.search_publications(
            search_term=search_term, session=session
        )

        company = crud_company.get_company_by_vat_number(
            vat_number=company_vatnumber, session=session
        )

        return [
            convert_publication_to_out_schema_with_company(
                publication=publication, company=company
            )
            for publication in publications
        ]


@publications_router.post("/conversation", response_model=ConversationResponse)
async def conversation_with_files(
    request: ConversationRequest,
    background_tasks: BackgroundTasks,
    client: OpenAI = Depends(get_openai_client),
):
    """
    API endpoint to have a conversation with procurement files.
    Allows users to ask questions about the files and get responses.
    Only requires publication_id - files are fetched automatically.
    """
    try:
        publication_id = request.publication_id
        thread_id = None

        # Check if we already have an active session for this publication
        if publication_id in active_sessions and not request.thread_id:
            # Clean up the old session if starting a new conversation without a thread_id
            background_tasks.add_task(cleanup_session, publication_id, client)
            # Remove from active sessions immediately to prevent conflicts
            if publication_id in active_sessions:
                del active_sessions[publication_id]

        # If no thread_id is provided or the publication isn't in active sessions, create a new session
        if not request.thread_id or publication_id not in active_sessions:
            # Fetch documents for this publication
            async with httpx.AsyncClient() as http_client:
                filesmap = await get_publication_workspace_documents(
                    http_client, publication_id
                )

            # Create a new vector store
            vector_store = client.beta.vector_stores.create(
                name=f"publication_{publication_id}"
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
            assistant = client.beta.assistants.update(
                assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
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

            # Store the session information
            active_sessions[publication_id] = {
                "vector_store_id": vector_store.id,
                "thread_id": thread_id,
            }

        else:
            # Continue an existing conversation
            thread_id = request.thread_id

            # Verify the thread exists in our active sessions
            if active_sessions.get(publication_id, {}).get("thread_id") != thread_id:
                raise HTTPException(
                    status_code=404, detail="Thread not found for this publication"
                )

            # Add the new message to the existing thread
            client.beta.threads.messages.create(
                thread_id=thread_id, role="user", content=request.message
            )

        # Create and poll the run
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B"
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


@publications_router.delete("/conversation/{publication_id}")
async def end_conversation(
    publication_id: str, client: OpenAI = Depends(get_openai_client)
):
    """
    End a conversation and clean up resources for a specific publication.
    """
    if publication_id not in active_sessions:
        raise HTTPException(
            status_code=404, detail="No active conversation for this publication"
        )

    await cleanup_session(publication_id, client)
    return {"message": "Conversation ended and resources cleaned up"}


@publications_router.get("/publications/{publication_id}/files")
async def get_publication_files(publication_id: str):
    """
    Get files for a publication by ID.
    This endpoint is used by the frontend to check available files.
    """
    try:
        async with httpx.AsyncClient() as client:
            filesmap = await get_publication_workspace_documents(client, publication_id)

            # Return only file names to avoid sending large file content
            file_names = {name: {"name": name} for name in filesmap.keys()}
            return file_names

    except Exception as e:
        logging.error(f"Error fetching publication files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def cleanup_session(publication_id: str, client: OpenAI):
    """
    Helper function to clean up resources when a conversation ends.
    """
    try:
        if publication_id in active_sessions:
            session = active_sessions[publication_id]

            # Clean up the assistant
            client.beta.assistants.update(
                assistant_id="asst_OMvTxo3W1byW40gTiceOzP8B",
                tool_resources={"file_search": {"vector_store_ids": []}},
            )

            # Delete the vector store
            if "vector_store_id" in session:
                client.beta.vector_stores.delete(
                    vector_store_id=session["vector_store_id"]
                )

            # Clean up any uploaded files
            files = client.files.list()
            for file in files:
                client.files.delete(file.id)

            # Remove the session from our tracking
            del active_sessions[publication_id]

    except Exception as e:
        logging.error(f"Error cleaning up session: {e}")
        raise
