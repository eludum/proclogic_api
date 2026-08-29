"""The LLM retrieval loop behind "Vergelijkbare gunningen".

What this replaces: a hand-tuned SQL CASE sum in app/crud/publication_related.py
that awarded 50 points for the same buyer, 35 for a shared keyword, 25 for a
matching CPV code, and never once compared the text of two tenders. Its output
was rendered to users as a "% match".

What happens instead:

  1. A deterministic query pulls a broad candidate pool. Recall only.
  2. The model looks at that pool and issues its own searches against the same
     database -- reformulating in Dutch, widening the CPV, dropping the value
     band -- until it has seen enough.
  3. The model ranks what it found and explains each choice in Dutch.
  4. The response is rebuilt from the database rows.

The model chooses and explains. It never supplies data. Any id it returns that
did not come out of a tool result is dropped before assembly, so a gunning that
does not exist cannot reach the frontend -- which is the entire point of the
exercise.
"""

import asyncio
import json
import logging
import pickle
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import joinedload

from app.ai.openai import get_async_openai_client
from app.ai.recommend import handle_json_response_formats
from app.config.postgres import get_session
from app.config.redis_manager import get_redis_client
from app.config.settings import settings
from app.crud.publication_contract import get_paginated_contracts
from app.crud.publication_related import get_related_awarded_contracts
from app.mcp import load_tools
from app.mcp.client import call_tool_as_text
from app.mcp.context import ANONYMOUS, ToolContext
from app.mcp.registry import get_tool
from app.mcp.tools.serializers import award_to_dict, candidate_to_dict
from app.models.publication_contract_models import Contract
from app.models.publication_models import Publication
from app.util.publication_utils.contract import get_publication_title
from app.util.publication_utils.publication_converter import PublicationConverter

logger = logging.getLogger(__name__)

# The subset of tools the retrieval loop may use. Deliberately narrow: this loop
# has one job, and a model given the whole registry will wander into company
# profiles and timeseries instead of finding comparable awards.
RETRIEVAL_TOOLS = (
    "search_awards",
    "award_market_stats",
    "awards_by_winner",
    "lookup_cpv",
    "lookup_nuts",
)

_SYSTEM_PROMPT = """Je bent een zoekagent voor Belgische overheidsopdrachten.

Je krijgt één aanbesteding te zien. Je taak: vind in de database de gegunde
opdrachten (gunningen) die er echt op lijken, en leg per resultaat uit waarom.

Werkwijze:
- Je krijgt een eerste set kandidaten. Die is ruw en onvolledig.
- Gebruik search_awards om zelf verder te zoeken. Varieer je zoektermen: gebruik
  de woorden die in het bestek zouden staan, probeer synoniemen, verbreed of
  versmal de CPV-code, laat de waardegrens vallen als je te weinig vindt.
- Zoek gerust meerdere keren. Je hebt een beperkt aantal beurten.

Wat "vergelijkbaar" betekent, in volgorde van belang:
1. Hetzelfde soort werk of levering (dit weegt het zwaarst -- lees de titels en
   beschrijvingen, vertrouw niet op de CPV-code alleen)
2. Vergelijkbare omvang en waarde
3. Vergelijkbare opdrachtgever of regio

Dezelfde opdrachtgever met totaal ander werk is NIET vergelijkbaar.
Hetzelfde werk bij een andere opdrachtgever WEL.

Antwoord uitsluitend met JSON, zonder omliggende tekst:
{"results": [{"workspace_id": "...", "relevance": 0-100, "reason": "..."}]}

- relevance is een echt percentage: 90+ betekent vrijwel dezelfde opdracht,
  60-80 duidelijk verwant werk, onder 40 niet opnemen.
- reason is één concrete Nederlandse zin die naar de inhoud verwijst
  ("Ook dakrenovatie van een schoolgebouw, vergelijkbare oppervlakte"), niet
  een herhaling van de criteria ("Zelfde CPV-code").
- Gebruik uitsluitend workspace_id's die je in zoekresultaten hebt gezien.
- Liever vijf goede resultaten dan twintig zwakke."""


# What to show while a given tool runs. Anything unlisted falls back to a
# generic line rather than leaking a function name into the UI.
_TOOL_LABELS = {
    "search_awards": "Gunningen doorzoeken",
    "search_publications": "Aanbestedingen doorzoeken",
    "find_similar_awards": "Vergelijkbare gunningen opzoeken",
    "find_similar_publications": "Vergelijkbare aanbestedingen opzoeken",
    "get_award": "Een gunning opvragen",
    "get_publication": "Een aanbesteding opvragen",
    "awards_by_sector": "Gunningen per sector bekijken",
    "awards_by_region": "Gunningen per regio bekijken",
    "awards_by_buyer": "Opdrachten van deze aanbestedende dienst bekijken",
    "awards_by_winner": "Eerdere winnaars bekijken",
    "search_organisations": "Organisaties opzoeken",
    "lookup_cpv": "CPV-codes opzoeken",
    "lookup_nuts": "Regiocodes opzoeken",
}


def _cache_key(workspace_id: str, limit: int) -> str:
    return f"similar_awards:{workspace_id}:{limit}"


def _cache_get(workspace_id: str, limit: int) -> Optional[List[Dict[str, Any]]]:
    try:
        raw = get_redis_client().get(_cache_key(workspace_id, limit))
        if raw:
            return pickle.loads(raw)
    except Exception as exc:
        logger.warning("similar_awards cache read failed for %s: %s", workspace_id, exc)
    return None


def _cache_set(workspace_id: str, limit: int, value: List[Dict[str, Any]]) -> None:
    try:
        get_redis_client().set(
            _cache_key(workspace_id, limit),
            pickle.dumps(value),
            ex=settings.similar_awards_cache_ttl,
        )
    except Exception as exc:
        logger.warning("similar_awards cache write failed for %s: %s", workspace_id, exc)


# ---------------------------------------------------------------------------
# Opt-in deep search
#
# The agent reads candidate awards and explains each match, and it is worth
# waiting for -- but it takes around 90 seconds, far past anything a page load
# can hold. So the page never runs it implicitly. It shows the deterministic
# scorer immediately, or a deep result that was computed earlier, and offers a
# button that starts one. The flag below is what lets the client poll for
# progress instead of holding a request open for a minute and a half.
# ---------------------------------------------------------------------------

class DeepProgress:
    """Real progress for the deep search, published to Redis as it happens.

    Not a timer. The steps below are the actual phases of the run -- loading the
    candidate pool, each tool-calling round the agent takes, and writing up the
    answer -- so the bar moves when work completes rather than when time passes.
    Rounds are not equal in length, so the bar is not linear in seconds; it is
    honest about progress, which is the thing a progress bar is for.

    ``awards_seen`` is the count of distinct awards the agent has actually pulled
    out of the database so far. It is the most informative number available and
    it only ever grows, so it reads as progress even mid-round.

    Every write is best-effort: this is telemetry for a spinner, and it must
    never be the reason a search fails.
    """

    def __init__(self, workspace_id: str, limit: int):
        self.workspace_id = workspace_id
        self.limit = limit
        # prepare + one per round + finalise
        self.total = settings.retrieval_agent_max_rounds + 2
        self.step = 0

    def _key(self) -> str:
        return f"similar_awards_progress:{self.workspace_id}:{self.limit}"

    def publish(self, label: str, awards_seen: int = 0, advance: bool = True) -> None:
        if advance:
            self.step = min(self.step + 1, self.total)
        try:
            get_redis_client().set(
                self._key(),
                json.dumps(
                    {
                        "step": self.step,
                        "total": self.total,
                        "label": label,
                        "awards_seen": awards_seen,
                    }
                ),
                ex=int(settings.retrieval_agent_deep_timeout_seconds) + 60,
            )
        except Exception as exc:
            logger.debug("progress publish failed for %s: %s", self.workspace_id, exc)

    def clear(self) -> None:
        try:
            get_redis_client().delete(self._key())
        except Exception as exc:
            logger.debug("progress clear failed for %s: %s", self.workspace_id, exc)


def deep_progress(workspace_id: str, limit: int) -> Optional[Dict[str, Any]]:
    """The live progress of a running deep search, or None."""
    try:
        raw = get_redis_client().get(f"similar_awards_progress:{workspace_id}:{limit}")
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("progress read failed for %s: %s", workspace_id, exc)
    return None


STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_NONE = "none"


def _running_key(workspace_id: str, limit: int) -> str:
    return f"similar_awards_running:{workspace_id}:{limit}"


def deep_status(workspace_id: str, limit: int) -> str:
    """Whether a deep result exists, is being computed, or has never been asked for."""
    if _cache_get(workspace_id, limit) is not None:
        return STATUS_READY
    try:
        if get_redis_client().get(_running_key(workspace_id, limit)):
            return STATUS_RUNNING
    except Exception as exc:
        logger.warning("deep status check failed for %s: %s", workspace_id, exc)
    return STATUS_NONE


def _mark_running(workspace_id: str, limit: int) -> bool:
    """Claim the slot. False when another request already holds it.

    SET NX, so two people opening the same tender do not both pay for a run.
    The TTL is the ceiling on how long a crashed worker can block a retry.
    """
    try:
        return bool(
            get_redis_client().set(
                _running_key(workspace_id, limit),
                "1",
                ex=int(settings.retrieval_agent_deep_timeout_seconds) + 60,
                nx=True,
            )
        )
    except Exception as exc:
        logger.warning("deep lock failed for %s: %s", workspace_id, exc)
        # Without a lock we would rather run twice than never.
        return True


def _clear_running(workspace_id: str, limit: int) -> None:
    try:
        get_redis_client().delete(_running_key(workspace_id, limit))
    except Exception as exc:
        logger.warning("deep lock release failed for %s: %s", workspace_id, exc)


def cached_deep_results(
    workspace_id: str, limit: int
) -> Optional[List[Dict[str, Any]]]:
    """A previously computed deep result, if one is still cached."""
    return _cache_get(workspace_id, limit)


def deterministic_results(workspace_id: str, limit: int) -> List[Dict[str, Any]]:
    """The instant, rule-based comparison. No model involved."""
    return _fallback(workspace_id, limit)


async def run_deep_search(
    workspace_id: str, limit: int, ctx: Optional[ToolContext] = None
) -> None:
    """Run the agent and cache the result. Intended for a background task.

    Swallows everything: this runs detached from any request, so the only useful
    thing it can do with a failure is log it and release the lock, leaving the
    page on the deterministic list.
    """
    context = ctx or ANONYMOUS
    progress = DeepProgress(workspace_id, limit)
    try:
        results = await asyncio.wait_for(
            _find_similar_awards_uncached(workspace_id, limit, context, progress),
            timeout=settings.retrieval_agent_deep_timeout_seconds,
        )
        if results:
            _cache_set(workspace_id, limit, results)
            logger.info(
                "Deep similar-awards search stored %d result(s) for %s",
                len(results),
                workspace_id,
            )
        else:
            logger.info("Deep similar-awards search found nothing for %s", workspace_id)
    except asyncio.TimeoutError:
        logger.warning(
            "Deep similar-awards search timed out after %ss for %s",
            settings.retrieval_agent_deep_timeout_seconds,
            workspace_id,
        )
    except Exception as exc:
        logger.error(
            "Deep similar-awards search failed for %s: %s", workspace_id, exc,
            exc_info=exc,
        )
    finally:
        progress.clear()
        _clear_running(workspace_id, limit)


def start_deep_search(workspace_id: str, limit: int) -> str:
    """Claim the slot for a deep run. Returns the status to report to the client."""
    existing = _cache_get(workspace_id, limit)
    if existing is not None:
        return STATUS_READY
    if not _mark_running(workspace_id, limit):
        return STATUS_RUNNING
    return "started"


def invalidate_similar_awards_cache(workspace_id: str) -> None:
    """Drop every cached limit variant for one publication."""
    try:
        client = get_redis_client()
        for key in client.scan_iter(match=f"similar_awards:{workspace_id}:*"):
            client.delete(key)
    except Exception as exc:
        logger.warning("similar_awards cache invalidation failed for %s: %s", workspace_id, exc)


def _describe_source(publication: Publication) -> Dict[str, Any]:
    """The compact profile of the tender we are finding comparables for."""
    description = None
    if publication.dossier and publication.dossier.descriptions:
        description = PublicationConverter.get_descr_as_str(
            publication.dossier.descriptions
        )

    organisation = None
    if publication.organisation and publication.organisation.organisation_names:
        organisation = PublicationConverter.get_org_name_as_str(
            publication.organisation.organisation_names
        )

    return {
        "workspace_id": publication.publication_workspace_id,
        "title": get_publication_title(publication),
        "description": (description or "")[:2000] or None,
        "buyer": organisation,
        "cpv_code": (
            publication.cpv_main_code.code if publication.cpv_main_code else None
        ),
        "regions": publication.nuts_codes or [],
        "estimated_value": publication.estimated_value,
        "keywords": publication.extracted_keywords or [],
        "lot_titles": [
            desc.text
            for lot in (publication.lots or [])[:10]
            for desc in (lot.titles or [])[:1]
            if getattr(desc, "text", None)
        ],
    }


def _seed_candidates(
    session, publication: Publication, pool_size: int
) -> List[Publication]:
    """Broad, cheap recall.

    Two passes, because either alone has a blind spot: full-text catches "same
    kind of work, different buyer", which the old scorer could never see, while
    the CPV pass catches awards whose text is too thin to match on.
    """
    title = get_publication_title(publication)
    cpv = publication.cpv_main_code.code if publication.cpv_main_code else None

    collected: Dict[str, Publication] = {}

    def _absorb(publications: List[Publication]) -> None:
        for pub in publications:
            if pub.publication_workspace_id == publication.publication_workspace_id:
                continue
            collected.setdefault(pub.publication_workspace_id, pub)

    if title and title != "Untitled":
        text_hits, _ = get_paginated_contracts(
            session=session,
            page=1,
            size=pool_size,
            search=title[:200],
            sort_by="relevance",
        )
        _absorb(text_hits)

    if cpv and len(collected) < pool_size:
        cpv_hits, _ = get_paginated_contracts(
            session=session,
            page=1,
            size=pool_size - len(collected),
            cpv_code=cpv[:5],
            sort_by="publication_date",
        )
        _absorb(cpv_hits)

    return list(collected.values())[:pool_size]


def _collect_workspace_ids(payload: Any, into: Set[str]) -> None:
    """Walk a tool result and record every workspace id the model was shown.

    This set is the whitelist for the final answer. Anything outside it was
    invented.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in ("workspace_id", "publication_id") and isinstance(value, str):
                into.add(value)
            else:
                _collect_workspace_ids(value, into)
    elif isinstance(payload, list):
        for item in payload:
            _collect_workspace_ids(item, into)


def _parse_results(content: str) -> List[Dict[str, Any]]:
    """Pull the ranked list out of the model's final message."""
    if not content:
        return []

    # handle_json_response_formats strips a ```json fence and returns the parsed
    # object -- it does not return a string, and it raises on anything it cannot
    # decode.
    try:
        parsed = handle_json_response_formats(content)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Retrieval agent returned unparseable JSON: %r", content[:300])
        return []

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("results", "similar_awards", "awards"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return []


def _load_awards(workspace_ids: List[str]) -> Dict[str, Publication]:
    if not workspace_ids:
        return {}

    with get_session() as session:
        rows = (
            session.query(Publication)
            .filter(
                Publication.publication_workspace_id.in_(workspace_ids),
                Publication.contract_id.isnot(None),
            )
            .options(
                joinedload(Publication.dossier),
                joinedload(Publication.organisation),
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.contract).joinedload(Contract.winning_publisher),
                joinedload(Publication.contract).joinedload(
                    Contract.contracting_authority
                ),
                joinedload(Publication.contract).joinedload(Contract.service_provider),
            )
            .all()
        )
        return {
            pub.publication_workspace_id: award_to_dict(pub) for pub in rows
        }


def _fallback(workspace_id: str, limit: int) -> List[Dict[str, Any]]:
    """The old deterministic scorer, kept as a safety net.

    If the model is slow, unreachable or produces nothing usable, the block on
    the tender page degrades to what it showed before this change rather than to
    an empty state.
    """
    logger.info("Falling back to deterministic similarity for %s", workspace_id)
    try:
        with get_session() as session:
            publication = (
                session.query(Publication)
                .filter(Publication.publication_workspace_id == workspace_id)
                .options(
                    joinedload(Publication.cpv_main_code),
                    joinedload(Publication.dossier),
                    joinedload(Publication.organisation),
                )
                .first()
            )
            if publication is None:
                return []

            related = get_related_awarded_contracts(
                publication=publication, session=session, limit=limit
            )

            results = []
            for pub, score, reason in related:
                if not pub.contract:
                    continue
                # The raw score is a point total on an open-ended scale, not a
                # percentage. Cap it so the frontend badge stays honest.
                results.append(
                    dict(
                        award_to_dict(pub),
                        similarity_score=min(float(score), 100.0),
                        similarity_reason=reason,
                    )
                )
            return results
    except Exception as exc:
        logger.error("Deterministic fallback failed for %s: %s", workspace_id, exc)
        return []


async def _run_agent(
    source: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    seen_ids: Set[str],
    limit: int,
    ctx: ToolContext,
    progress: Optional["DeepProgress"] = None,
) -> List[Dict[str, Any]]:
    """The tool-calling loop. Returns the model's raw ranked list."""
    load_tools()
    client = get_async_openai_client()

    tool_specs = [
        tool.to_openai_spec()
        for tool in (get_tool(name) for name in RETRIEVAL_TOOLS)
        if tool is not None
    ]

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Aanbesteding waarvoor je vergelijkbare gunningen zoekt:\n"
                f"{json.dumps(source, ensure_ascii=False, default=str)}\n\n"
                f"Eerste kandidaten uit de database "
                f"({len(candidates)} stuks):\n"
                f"{json.dumps(candidates, ensure_ascii=False, default=str)}\n\n"
                f"Geef maximaal {limit} resultaten."
            ),
        },
    ]

    for round_index in range(settings.retrieval_agent_max_rounds):
        if progress:
            progress.publish(
                f"Zoekopdracht {round_index + 1} van "
                f"{settings.retrieval_agent_max_rounds} voorbereiden...",
                awards_seen=len(seen_ids),
            )
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tool_specs,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ]
                or None,
            }
        )

        if not tool_calls:
            # The agent is answering rather than searching again: the remaining
            # rounds will not happen, so jump the bar to the write-up phase
            # instead of leaving it stuck where it was.
            if progress:
                progress.step = progress.total - 1
                progress.publish(
                    "Resultaten onderbouwen...", awards_seen=len(seen_ids), advance=False
                )
            return _parse_results(message.content or "")

        for call in tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            if progress:
                progress.publish(
                    f"{_TOOL_LABELS.get(call.function.name, 'De databank doorzoeken')}...",
                    awards_seen=len(seen_ids),
                    advance=False,
                )

            payload = await call_tool_as_text(call.function.name, arguments, ctx)

            try:
                _collect_workspace_ids(json.loads(payload), seen_ids)
            except (json.JSONDecodeError, TypeError):
                pass

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": payload,
                }
            )

        logger.debug(
            "Retrieval round %d: %d tool calls, %d ids seen",
            round_index + 1,
            len(tool_calls),
            len(seen_ids),
        )

    # Rounds exhausted. Force an answer with the evidence already gathered
    # instead of returning nothing.
    if progress:
        progress.publish("Resultaten onderbouwen...", awards_seen=len(seen_ids))
    messages.append(
        {
            "role": "user",
            "content": (
                "Je hebt geen zoekbeurten meer. Geef nu je eindantwoord als JSON "
                "op basis van wat je al gevonden hebt."
            ),
        }
    )
    final = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        tool_choice="none",
        tools=tool_specs,
    )
    return _parse_results(final.choices[0].message.content or "")


async def find_similar_awards(
    workspace_id: str,
    limit: int = 10,
    ctx: Optional[ToolContext] = None,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """Awards comparable to the given tender, as ranked by the model.

    Every entry is a real database row. Only similarity_score and
    similarity_reason come from the model.
    """
    limit = max(1, min(int(limit or 10), 20))
    context = ctx or ANONYMOUS

    if use_cache:
        cached = _cache_get(workspace_id, limit)
        if cached is not None:
            return cached

    try:
        results = await asyncio.wait_for(
            _find_similar_awards_uncached(workspace_id, limit, context),
            timeout=settings.retrieval_agent_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Retrieval agent timed out after %ss for %s",
            settings.retrieval_agent_timeout_seconds,
            workspace_id,
        )
        results = []
    except Exception as exc:
        logger.error("Retrieval agent failed for %s: %s", workspace_id, exc, exc_info=exc)
        results = []

    if not results:
        results = await asyncio.to_thread(_fallback, workspace_id, limit)

    if results and use_cache:
        _cache_set(workspace_id, limit, results)

    return results


def _prepare(workspace_id: str, pool_size: int):
    """Load the source tender and its candidate pool. Runs off the event loop."""
    with get_session() as session:
        publication = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id == workspace_id)
            .options(
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.dossier),
                joinedload(Publication.organisation),
                joinedload(Publication.lots),
            )
            .first()
        )
        if publication is None:
            return None, [], set()

        source = _describe_source(publication)
        candidate_rows = _seed_candidates(session, publication, pool_size)
        candidates = [candidate_to_dict(pub) for pub in candidate_rows]
        seen = {c["workspace_id"] for c in candidates}
        return source, candidates, seen


async def _find_similar_awards_uncached(
    workspace_id: str, limit: int, ctx: ToolContext,
    progress: Optional["DeepProgress"] = None,
) -> List[Dict[str, Any]]:
    pool_size = settings.retrieval_agent_max_candidates
    if progress:
        progress.publish("Aanbesteding en eerste kandidaten laden...")
    source, candidates, seen_ids = await asyncio.to_thread(
        _prepare, workspace_id, pool_size
    )

    if source is None:
        logger.info("find_similar_awards: no publication %s", workspace_id)
        return []

    ranked = await _run_agent(source, candidates, seen_ids, limit, ctx, progress)
    if not ranked:
        return []

    # Drop anything the model did not actually see. This is the guard that keeps
    # a hallucinated gunning off the page.
    accepted: List[Dict[str, Any]] = []
    for entry in ranked:
        if not isinstance(entry, dict):
            continue
        candidate_id = entry.get("workspace_id") or entry.get("publication_id")
        if not candidate_id:
            continue
        if candidate_id == workspace_id:
            continue
        if candidate_id not in seen_ids:
            logger.warning(
                "Retrieval agent returned unseen workspace_id %r for %s; dropping",
                candidate_id,
                workspace_id,
            )
            continue
        accepted.append(entry)

    accepted.sort(key=lambda e: float(e.get("relevance") or 0), reverse=True)
    accepted = accepted[:limit]

    if progress:
        progress.publish(
            f"{len(accepted)} gunning(en) ophalen...",
            awards_seen=len(seen_ids),
            advance=False,
        )
    awards = await asyncio.to_thread(
        _load_awards, [e["workspace_id"] for e in accepted]
    )

    results: List[Dict[str, Any]] = []
    for entry in accepted:
        award = awards.get(entry["workspace_id"])
        if award is None:
            # Passed the whitelist but is not an award row -- e.g. the model
            # picked up an id from a tool that returns open tenders.
            continue
        try:
            score = float(entry.get("relevance") or 0)
        except (TypeError, ValueError):
            score = 0.0
        results.append(
            dict(
                award,
                similarity_score=max(0.0, min(score, 100.0)),
                similarity_reason=(entry.get("reason") or "").strip()
                or "Vergelijkbare opdracht",
            )
        )

    return results


def find_similar_awards_sync(
    workspace_id: str, limit: int = 10, ctx: Optional[ToolContext] = None
) -> List[Dict[str, Any]]:
    """Synchronous entry point for the MCP tool handler.

    Tool handlers are dispatched via asyncio.to_thread, so there is no running
    loop on this thread and asyncio.run is safe. Guarded anyway.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(find_similar_awards(workspace_id, limit, ctx))

    raise RuntimeError(
        "find_similar_awards_sync called from a running event loop; "
        "await find_similar_awards() instead."
    )
