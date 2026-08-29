import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from app.config.settings import settings
from app.mcp import load_tools
from app.mcp.client import call_tool_as_text
from app.mcp.context import ANONYMOUS, ToolContext
from app.mcp.registry import openai_tool_specs
from app.models.company_models import Company
from app.models.conversation_models import Conversation
from app.models.publication_models import Publication
from app.util.publication_utils.publication_converter import PublicationConverter

logger = logging.getLogger(__name__)

# Emitted so the UI can say what Procy is doing mid-turn. Optional: the caller
# passes a coroutine or nothing at all.
EventCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]


# The document summary is the single largest thing in the prompt and the history
# is replayed on every turn, so it is bounded. Procy can always call
# get_publication for the rest.
MAX_SUMMARY_CHARS = 6000


def _truncate(text: Optional[str], limit: int = MAX_SUMMARY_CHARS) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[...ingekort, vraag door voor meer detail]"


def _tender_content(publication: Publication, pub_data) -> str:
    """The actual substance of the tender, not just its metadata.

    This was missing entirely. The prompt carried the title, the deadline and the
    CPV code, and nothing else -- so the assistant on a document-analysis product
    could not see a single word of the tender it was being asked about, while the
    chat window listed the document filenames as though it could.
    """
    parts = []

    description = getattr(pub_data, "original_description", None)
    if description:
        parts.append(f"BESCHRIJVING VAN DE OPDRACHT:\n{_truncate(description, 4000)}")

    summary = publication.ai_summary_without_documents
    if summary:
        parts.append(f"SAMENVATTING VAN DE AANKONDIGING:\n{_truncate(summary)}")

    doc_summary = publication.ai_summary_with_documents
    if doc_summary:
        parts.append(
            "SAMENVATTING VAN DE BESTEKDOCUMENTEN:\n" + _truncate(doc_summary)
        )

    documents = getattr(pub_data, "documents", None)
    if documents:
        listed = ", ".join(documents[:25])
        parts.append(f"BESCHIKBARE DOCUMENTEN ({len(documents)}): {listed}")

    if not parts:
        return "Er is geen beschrijving of documentinhoud beschikbaar voor deze opdracht."

    return "\n\n".join(parts)


def build_system_prompt(company: Company, publication: Publication) -> str:
    pub_data = PublicationConverter.to_output_schema(publication, company)

    return f"""You are Procy, an assistant for Belgian public procurement, helping {company.name}.

You have LIVE READ ACCESS to the ProcLogic database through your tools. It holds
every published Belgian tender and every awarded contract (gunning), with buyers,
winners, values and dates.

The conversation started from the tender below, but you are not limited to it.
When the user asks about comparable work, past awards, what things cost, who
tends to win, or what else is open, search the database.

TENDER IN FOCUS:
- Workspace ID: {publication.publication_workspace_id}
- Title: {pub_data.title}
- Organization: {pub_data.organisation}
- Submission deadline: {pub_data.submission_deadline}
- CPV code: {pub_data.cpv_code}
- Sector: {pub_data.sector}
- Estimated value: {pub_data.estimated_value if pub_data.estimated_value else "Unknown"}

{_tender_content(publication, pub_data)}

COMPANY YOU ARE HELPING:
- Name: {company.name}
- VAT: {company.vat_number}
- Activities: {company.summary_activities}
- Interested sectors: {', '.join(sector.sector for sector in company.interested_sectors)}
- Accreditations: {company.accreditations if company.accreditations else 'None'}
- Regions: {', '.join(company.operating_regions) if company.operating_regions else 'Not specified'}

USING YOUR TOOLS:
- The description and document summaries above are the content of THIS tender.
  Answer questions about its requirements, scope and criteria from them directly;
  there is no need to search for the tender you are already looking at.
- Never answer a factual question about OTHER tenders, awards, companies, values
  or market trends from memory. Look it up. You have the database; use it.
- find_similar_awards is the right tool for "what comparable work has been
  awarded before" and for questions about what such work costs.
- awards_by_winner answers "who usually wins this kind of work".
- lookup_cpv and lookup_nuts resolve sector and region codes. Use them before
  filtering, so you filter on a code that exists.
- If a search returns nothing, say so plainly and try a broader one. Never
  invent a plausible-looking result to fill the gap.
- If your first search returns little, reformulate: different Dutch wording, a
  broader CPV code, a wider value range.

CITING WHAT YOU FIND:
- Every tender or gunning you mention must be named and linked, as a markdown
  link using the `url` field from the tool result:
  [Titel van de opdracht](https://...)
- Give concrete figures with their source: amount, year, and the winner or buyer.

GUIDELINES:
- Always respond in Dutch unless specifically asked to use another language
- Be concise but complete
- Tailor advice to this company's profile, capabilities and accreditations
- Distinguish clearly between what you found in the database and what is your
  own judgement
"""


def build_conversation_history(
    conversation: Conversation, company: Company, publication: Publication
) -> List[Dict[str, Any]]:
    """Build conversation history from database messages with system prompt.

    Only the most recent chat_history_max_messages turns are replayed. Replaying
    everything was affordable when a turn was a single completion; with tool
    results in the loop, a long conversation would grow the context without
    bound.
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(company, publication)}
    ]

    history = sorted(conversation.messages, key=lambda m: m.created_at)
    window = settings.chat_history_max_messages
    if window and len(history) > window:
        history = history[-window:]

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    return messages


def _tool_specs() -> List[Dict[str, Any]]:
    if not settings.mcp_enabled:
        return []
    load_tools()
    return openai_tool_specs()


def _assistant_message(content: Optional[str], tool_calls: List[Dict[str, Any]]):
    message: Dict[str, Any] = {"role": "assistant", "content": content or ""}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


async def _run_tool_calls(
    tool_calls: List[Dict[str, Any]],
    ctx: ToolContext,
    on_event: Optional[EventCallback],
) -> List[Dict[str, Any]]:
    """Dispatch the model's tool calls and return the tool messages."""
    results = []
    for call in tool_calls:
        name = call["function"]["name"]
        raw_arguments = call["function"].get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            logger.info("Model sent unparseable arguments for %s: %r", name, raw_arguments)
            arguments = {}

        if on_event is not None:
            try:
                await on_event("tool_call", {"tool": name, "arguments": arguments})
            except Exception as exc:
                # A UI notification must never break the turn.
                logger.debug("tool_call event callback failed: %s", exc)

        payload = await call_tool_as_text(name, arguments, ctx)
        results.append(
            {"role": "tool", "tool_call_id": call["id"], "content": payload}
        )

    return results


def _accumulate_tool_calls(
    delta_tool_calls, accumulator: Dict[int, Dict[str, Any]]
) -> None:
    """Fold streamed tool-call deltas into whole calls.

    The API streams a tool call in pieces: the name arrives once, the JSON
    arguments arrive a few characters at a time, and the index ties them
    together.
    """
    for delta in delta_tool_calls:
        index = delta.index
        entry = accumulator.setdefault(
            index, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
        )
        if delta.id:
            entry["id"] = delta.id
        if delta.function is not None:
            if delta.function.name:
                entry["function"]["name"] = delta.function.name
            if delta.function.arguments:
                entry["function"]["arguments"] += delta.function.arguments


async def process_ai_message(
    conversation: Conversation,
    user_message: str,
    company: Company,
    publication: Publication,
    client: AsyncOpenAI,
    ctx: Optional[ToolContext] = None,
) -> Tuple[str, Optional[str]]:
    """Process a message with OpenAI Chat Completions API and return response."""
    messages = build_conversation_history(conversation, company, publication)
    messages.append({"role": "user", "content": user_message})

    context = ctx or ANONYMOUS
    tools = _tool_specs()

    for _ in range(settings.chat_agent_max_rounds):
        kwargs: Dict[str, Any] = {"model": settings.openai_model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        tool_calls = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in (message.tool_calls or [])
        ]

        if not tool_calls:
            return message.content or "", None

        messages.append(_assistant_message(message.content, tool_calls))
        messages.extend(await _run_tool_calls(tool_calls, context, None))

    # Rounds exhausted: answer from what has been gathered.
    final_kwargs: Dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
    }
    if tools:
        final_kwargs["tools"] = tools
        final_kwargs["tool_choice"] = "none"
    response = await client.chat.completions.create(**final_kwargs)
    return response.choices[0].message.content or "", None


async def stream_ai_response(
    conversation: Conversation,
    user_message: str,
    company: Company,
    publication: Publication,
    client: AsyncOpenAI,
    ctx: Optional[ToolContext] = None,
    on_event: Optional[EventCallback] = None,
):
    """Stream a response from OpenAI, running tool calls as the model requests them.

    Yields ``(content_chunk, citations)`` tuples.

    Errors propagate. They used to be swallowed into a Dutch apology that was
    yielded as if the model had said it, which the websocket handler then
    persisted as an assistant message -- so a transient API failure became a
    permanent part of the conversation. The caller sends an error frame instead.
    """
    logger.info("Stream AI: Starting with message: '%s...'", user_message[:30])

    messages = build_conversation_history(conversation, company, publication)
    messages.append({"role": "user", "content": user_message})

    context = ctx or ANONYMOUS
    tools = _tool_specs()

    for round_index in range(settings.chat_agent_max_rounds):
        kwargs: Dict[str, Any] = {
            "model": settings.openai_model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**kwargs)

        content_parts: List[str] = []
        pending: Dict[int, Dict[str, Any]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content_parts.append(delta.content)
                yield delta.content, []

            if getattr(delta, "tool_calls", None):
                _accumulate_tool_calls(delta.tool_calls, pending)

        tool_calls = [pending[index] for index in sorted(pending) if pending[index]["id"]]

        if not tool_calls:
            logger.info("Stream AI: Completed streaming response")
            return

        # Any text streamed alongside the tool calls has already reached the
        # client; keep it in the history so the model sees what it said.
        messages.append(_assistant_message("".join(content_parts), tool_calls))
        messages.extend(await _run_tool_calls(tool_calls, context, on_event))

        logger.info(
            "Stream AI: round %d ran %d tool call(s): %s",
            round_index + 1,
            len(tool_calls),
            ", ".join(call["function"]["name"] for call in tool_calls),
        )

    # Rounds exhausted: stream a final answer with tools switched off so the
    # model cannot spend another round searching.
    logger.info("Stream AI: tool rounds exhausted, forcing final answer")
    final_kwargs: Dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        # The history contains tool_calls, so the schema has to stay attached;
        # tool_choice="none" is what stops another round of searching.
        final_kwargs["tools"] = tools
        final_kwargs["tool_choice"] = "none"
    final_stream = await client.chat.completions.create(**final_kwargs)
    async for chunk in final_stream:
        if not chunk.choices:
            continue
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content, []


def get_publication_title(publication: Publication) -> str:
    """Extract publication title from publication object."""
    if publication and publication.dossier and publication.dossier.titles:
        for title in publication.dossier.titles:
            if title.language in settings.prefered_languages_descriptions:
                return title.text
    return "Untitled Publication"
