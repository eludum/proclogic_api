import pickle
from functools import wraps
from typing import Callable, Optional
import logging
import io

from redis.client import Redis
from app.config.redis_manager import get_redis_client, get_binary_redis_client

# Cache TTL in seconds
CACHE_TTL = 24 * 60 * 60
CONVERSATION_TTL = 7 * 24 * 60 * 60  # 7 days for conversation persistence


def redis_cache(key_prefix: str, ttl: int = CACHE_TTL, id_arg_index: int = 1):
    """
    Decorator for caching async function results in Redis.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if we're caching documents
            is_document_func = "documents" in key_prefix

            # Extract the ID from arguments
            if len(args) > id_arg_index:
                entity_id = args[id_arg_index]
            elif "publication_workspace_id" in kwargs:
                entity_id = kwargs["publication_workspace_id"]
            elif "forum_id" in kwargs:
                entity_id = kwargs["forum_id"]
            else:
                # If no ID found, just call the original function
                return await func(*args, **kwargs)

            # Create a cache key
            cache_key = f"{key_prefix}:{entity_id}"

            # Get appropriate Redis client based on data type
            if is_document_func:
                # Use binary client for document data
                redis_client = get_binary_redis_client()
            else:
                # Use text client for forum, agent, etc.
                redis_client = get_redis_client()

            # Try to get from cache
            if is_document_func:
                # Handle binary file data
                try:
                    raw_data = redis_client.get(cache_key)
                    if raw_data:
                        serialized_data = pickle.loads(raw_data)

                        # Reconstruct BytesIO objects
                        reconstructed_files = {}
                        for file_name, file_data in serialized_data.items():
                            try:
                                bytes_io = io.BytesIO(file_data["content"])
                                bytes_io.name = file_data["name"]
                                reconstructed_files[file_name] = bytes_io
                            except (KeyError, TypeError) as e:
                                logging.warning(
                                    f"Error reconstructing file {file_name}: {str(e)}"
                                )
                                continue

                        if reconstructed_files:
                            return reconstructed_files
                except Exception as e:
                    logging.warning(
                        f"Document cache retrieval failed for {cache_key}: {str(e)}"
                    )
            else:
                # Handle forum and all other data types
                try:
                    raw_data = redis_client.get(cache_key)
                    if raw_data:
                        # For text client, raw_data is already a string that needs encoding
                        return pickle.loads(
                            raw_data.encode("utf-8")
                            if isinstance(raw_data, str)
                            else raw_data
                        )
                except Exception as e:
                    logging.warning(f"Cache retrieval failed for {cache_key}: {str(e)}")

            # Cache miss or error - call the original function
            result = await func(*args, **kwargs)

            # Cache the result if we got something
            if result:
                try:
                    if is_document_func:
                        # Serialize file objects
                        serialized_files = {}
                        for file_name, file_obj in result.items():
                            try:
                                # Save current position
                                current_pos = file_obj.tell()
                                # Read all content
                                file_obj.seek(0)
                                content = file_obj.read()
                                # Restore position
                                file_obj.seek(current_pos)

                                serialized_files[file_name] = {
                                    "content": content,
                                    "name": getattr(file_obj, "name", file_name),
                                }
                            except Exception as e:
                                logging.warning(
                                    f"Error serializing {file_name}: {str(e)}"
                                )
                                continue

                        if serialized_files:
                            redis_client.set(
                                cache_key, pickle.dumps(serialized_files), ex=ttl
                            )
                    else:
                        # For forum and all other data types
                        redis_client.set(cache_key, pickle.dumps(result), ex=ttl)
                except Exception as e:
                    logging.warning(f"Cache storage failed for {cache_key}: {str(e)}")

            return result

        return wrapper

    return decorator


def invalidate_publication_cache(publication_workspace_id: str):
    """
    Invalidate Redis cache entries related to a specific publication workspace ID.
    """
    # Need to delete from both Redis clients to ensure complete cleanup
    binary_redis = get_binary_redis_client()
    text_redis = get_redis_client()

    keys_to_delete = [
        f"pubproc:documents:{publication_workspace_id}",
        f"pubproc:forum:{publication_workspace_id}",
    ]

    # Delete keys from both clients
    if keys_to_delete:
        binary_redis.delete(*keys_to_delete)
        text_redis.delete(*keys_to_delete)


# Functions for conversation thread management
def get_thread_id(
    redis: Redis, vat_number: str, publication_workspace_id: str
) -> Optional[str]:
    """Get thread ID from Redis if it exists"""
    thread_key = f"thread:{vat_number}:{publication_workspace_id}"
    thread_id = redis.get(thread_key)
    return thread_id.decode() if thread_id else None


def store_thread_id(
    redis: Redis, vat_number: str, publication_workspace_id: str, thread_id: str
) -> None:
    """Store thread ID in Redis with TTL"""
    thread_key = f"thread:{vat_number}:{publication_workspace_id}"
    redis.set(thread_key, thread_id, ex=CONVERSATION_TTL)


def refresh_thread_ttl(
    redis: Redis, vat_number: str, publication_workspace_id: str
) -> None:
    """Refresh TTL for thread ID in Redis"""
    thread_key = f"thread:{vat_number}:{publication_workspace_id}"
    redis.expire(thread_key, CONVERSATION_TTL)
