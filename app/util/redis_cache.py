import pickle
from functools import wraps
from io import BytesIO
from typing import Callable
import logging

from app.config.redis_manager import get_redis_client
from app.util.redis_utils import (
    decode_base64_to_bytesio,
    read_file_bytes,
)

# Cache TTL in seconds (24 hours).
# TODO: revisit cadence — re-check saved publications daily?
CACHE_TTL = 24 * 60 * 60

# Hard ceiling on a single cached entry. The pubproc:documents cache used to
# store whole document sets (hundreds of MB each) with no limit, which grew
# Redis into its memory cap and got it OOMKilled (~every 11h). We now store raw
# bytes (no base64 inflation) and skip caching any entry above this size —
# oversized document sets are simply re-fetched on demand instead of cached.
MAX_CACHE_ENTRY_BYTES = 25 * 1024 * 1024  # 25 MiB


def _restore_documents(data: dict) -> dict:
    """
    Rebuild a {filename: BytesIO} map from a cached document entry so callers
    receive the same shape on a cache hit as on a miss. Handles both the new
    raw-bytes format and the legacy base64 format (older entries / fallback).
    """
    restored = {}
    for filename, payload in data.items():
        if isinstance(payload, dict) and "content_bytes" in payload:
            file_obj = BytesIO(payload["content_bytes"])
            file_obj.name = payload.get("name", filename)
            restored[filename] = file_obj
        elif isinstance(payload, dict) and "content_base64" in payload:
            restored[filename] = decode_base64_to_bytesio(
                payload["content_base64"], filename=payload.get("name", filename)
            )
        else:
            # Already a usable object — leave as-is.
            restored[filename] = payload
    return restored


def redis_cache(key_prefix: str, ttl: int = CACHE_TTL, id_arg_index: int = 1):
    """
    Decorator for caching async function results in Redis.

    For pubproc:documents the file map is stored as raw bytes and transparently
    rebuilt into {filename: BytesIO} on read, so callers see an identical shape
    whether the result came fresh or from cache. Entries larger than
    MAX_CACHE_ENTRY_BYTES are not cached.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract the ID from arguments
            if len(args) > id_arg_index:
                entity_id = args[id_arg_index]
            elif "publication_workspace_id" in kwargs:
                entity_id = kwargs["publication_workspace_id"]
            else:
                # If no ID found, just call the original function
                return await func(*args, **kwargs)

            # Create a cache key
            cache_key = f"{key_prefix}:{entity_id}"

            # Get Redis client
            redis_client = get_redis_client()

            # Try to get from cache
            try:
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    try:
                        data = pickle.loads(cached_data)
                        if key_prefix == "pubproc:documents" and isinstance(data, dict):
                            return _restore_documents(data)
                        return data
                    except Exception as e:
                        logging.warning(f"Error unpickling data from cache: {str(e)}")
            except Exception as e:
                logging.warning(f"Cache retrieval failed for {cache_key}: {str(e)}")

            # Cache miss or error - call the original function
            result = await func(*args, **kwargs)

            if not result:
                return result

            # Cache the result, skipping anything over the size cap.
            try:
                if key_prefix == "pubproc:documents" and isinstance(result, dict):
                    # Store document files as RAW bytes (not base64).
                    serialized_files = {}
                    total_bytes = 0
                    for filename, file_obj in result.items():
                        try:
                            content = read_file_bytes(file_obj)
                        except Exception as e:
                            logging.warning(
                                f"Error reading {filename} for cache: {str(e)}"
                            )
                            continue
                        serialized_files[filename] = {
                            "content_bytes": content,
                            "name": getattr(file_obj, "name", filename),
                        }
                        total_bytes += len(content)

                    if not serialized_files:
                        pass
                    elif total_bytes > MAX_CACHE_ENTRY_BYTES:
                        logging.info(
                            f"Skip caching {cache_key}: {total_bytes} bytes "
                            f"exceeds {MAX_CACHE_ENTRY_BYTES} cap"
                        )
                    else:
                        redis_client.set(
                            cache_key, pickle.dumps(serialized_files), ex=ttl
                        )
                else:
                    # For all other data types
                    payload = pickle.dumps(result)
                    if len(payload) > MAX_CACHE_ENTRY_BYTES:
                        logging.info(
                            f"Skip caching {cache_key}: {len(payload)} bytes "
                            f"exceeds {MAX_CACHE_ENTRY_BYTES} cap"
                        )
                    else:
                        redis_client.set(cache_key, payload, ex=ttl)
            except Exception as e:
                logging.warning(f"Cache storage failed for {cache_key}: {str(e)}")

            return result

        return wrapper

    return decorator


def invalidate_publication_cache(publication_workspace_id: str):
    """
    Invalidate Redis cache entries related to a specific publication workspace ID.
    """
    redis_client = get_redis_client()

    keys_to_delete = [
        f"pubproc:documents:{publication_workspace_id}",
    ]

    # Delete keys
    if keys_to_delete:
        redis_client.delete(*keys_to_delete)
