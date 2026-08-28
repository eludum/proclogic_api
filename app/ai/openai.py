from functools import lru_cache

from app.config.settings import settings
from openai import AsyncOpenAI, OpenAI

# Two tiers, because the two clients serve very different work.
#
# Sync: batch AI work (document summarisation over a full filesmap), which can
# legitimately run for minutes on a big tender. It is always dispatched through
# asyncio.to_thread, so a long call ties up a worker thread, never the event
# loop -- the SDK defaults are fine here and are set explicitly for the reader.
OPENAI_SYNC_TIMEOUT_SECONDS = 600.0
OPENAI_SYNC_MAX_RETRIES = 2

# Async: interactive request paths (website scrape, chat) where a user is
# waiting on the response. Bounded much tighter, and retried once.
OPENAI_ASYNC_TIMEOUT_SECONDS = 120.0
OPENAI_ASYNC_MAX_RETRIES = 1


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """Blocking client. Only call this from sync code, and only from an async
    context via asyncio.to_thread -- calling it directly on the event loop
    blocks the whole worker and starves the health probe."""
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=OPENAI_SYNC_TIMEOUT_SECONDS,
        max_retries=OPENAI_SYNC_MAX_RETRIES,
    )


@lru_cache(maxsize=1)
def get_async_openai_client() -> AsyncOpenAI:
    """Non-blocking client for use from any `async def`."""
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=OPENAI_ASYNC_TIMEOUT_SECONDS,
        max_retries=OPENAI_ASYNC_MAX_RETRIES,
    )
