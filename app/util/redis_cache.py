import pickle
from functools import wraps
from typing import Callable
import logging

from app.config.redis_manager import get_redis_client
from proclogic_api.app.util.redis_utils import (
    decode_base64_to_bytesio,
    encode_file_to_base64,
)

# Cache TTL in seconds (7 days default)
# TODO: increase, check daily for saved publications?
CACHE_TTL = 7 * 24 * 60 * 60


def redis_cache(key_prefix: str, ttl: int = CACHE_TTL, id_arg_index: int = 1):
    """
    Decorator for caching async function results in Redis.
    Files will be stored as base64 encoded strings.
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

                        # Special handling for document data
                        if key_prefix == "pubproc:documents" and isinstance(data, dict):
                            # Convert base64 back to file objects
                            reconstructed_files = {}
                            for filename, file_data in data.items():
                                if (
                                    isinstance(file_data, dict)
                                    and "content_base64" in file_data
                                ):
                                    # Create BytesIO from base64
                                    file_obj = decode_base64_to_bytesio(
                                        file_data["content_base64"]
                                    )

                                    # Set additional metadata
                                    if "name" in file_data:
                                        file_obj.name = file_data["name"]
                                    else:
                                        file_obj.name = filename

                                    reconstructed_files[filename] = file_obj
                                else:
                                    # Handle older cache format or malformed data
                                    reconstructed_files[filename] = file_data

                            return reconstructed_files
                        else:
                            # Return other data types as is
                            return data
                    except Exception as e:
                        logging.warning(f"Error unpickling data from cache: {str(e)}")
            except Exception as e:
                logging.warning(f"Cache retrieval failed for {cache_key}: {str(e)}")

            # Cache miss or error - call the original function
            result = await func(*args, **kwargs)

            # Cache the result if we got something
            if result:
                try:
                    if key_prefix == "pubproc:documents" and isinstance(result, dict):
                        # For document data, encode files to base64
                        serialized_files = {}
                        for filename, file_obj in result.items():
                            try:
                                # Store as a dict with base64 and metadata
                                serialized_files[filename] = {
                                    "content_base64": encode_file_to_base64(file_obj),
                                    "name": getattr(file_obj, "name", filename),
                                }
                            except Exception as e:
                                logging.warning(
                                    f"Error serializing {filename}: {str(e)}"
                                )
                                continue

                        if serialized_files:
                            redis_client.set(
                                cache_key, pickle.dumps(serialized_files), ex=ttl
                            )
                    else:
                        # For all other data types
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
    redis_client = get_redis_client()

    keys_to_delete = [
        f"pubproc:documents:{publication_workspace_id}",
    ]

    # Delete keys
    if keys_to_delete:
        redis_client.delete(*keys_to_delete)
