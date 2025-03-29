import pickle
from functools import wraps
from typing import Callable
import logging
import io

from app.config.redis_manager import get_redis_client, get_binary_redis_client

# Cache TTL in seconds
CACHE_TTL = 7 * 24 * 60 * 60


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
            if is_document_func or "forum" in key_prefix:
                # Use binary client for document data and forum data
                redis_client = get_binary_redis_client()
            else:
                # Use text client for other data types
                redis_client = get_redis_client()

            # Try to get from cache
            try:
                raw_data = redis_client.get(cache_key)
                if raw_data:
                    try:
                        # Always use pickle.loads directly on raw_data for binary data
                        return pickle.loads(raw_data)
                    except Exception as e:
                        logging.warning(f"Error unpickling data from cache: {str(e)}")
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
                                file_obj.seek(0, io.SEEK_SET)
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
