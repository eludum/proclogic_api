import pickle
from functools import wraps
from typing import Callable, Any

from app.config.redis_manager import get_redis_client

# Cache TTL in seconds
CACHE_TTL = 24 * 60 * 60


def redis_cache(key_prefix: str, ttl: int = CACHE_TTL, id_arg_index: int = 1):
    """
    Decorator for caching async function results in Redis.

    Args:
        key_prefix: Prefix for the Redis key
        ttl: Time-to-live in seconds
        id_arg_index: Index of the ID argument in the function arguments (after skipping client)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip first argument if it's 'self' or client
            skip_args = 1

            # Extract the ID (usually publication_workspace_id) from arguments
            if len(args) > id_arg_index:
                # Get ID from positional arguments
                entity_id = args[id_arg_index]
            elif "publication_workspace_id" in kwargs:
                # Get ID from keyword arguments
                entity_id = kwargs["publication_workspace_id"]
            elif "forum_id" in kwargs:
                # Get ID from keyword arguments (for forum)
                entity_id = kwargs["forum_id"]
            else:
                # If no ID found, use the original caching logic
                key_parts = [key_prefix, func.__name__]

                # Add arguments after the client
                for arg in args[skip_args:]:
                    key_parts.append(str(arg))

                # Add sorted keyword arguments
                if kwargs:
                    for k, v in sorted(kwargs.items()):
                        key_parts.append(f"{k}:{v}")

                cache_key = ":".join(key_parts)
                return await original_caching_logic(func, cache_key, *args, **kwargs)

            # Create a simpler cache key using only the key_prefix and entity_id
            cache_key = f"{key_prefix}:{entity_id}"

            return await original_caching_logic(func, cache_key, *args, **kwargs)

        async def original_caching_logic(
            func: Callable, cache_key: str, *args: Any, **kwargs: Any
        ):
            # Get Redis client
            redis = get_redis_client()

            # Try to get from cache
            cached_result = redis.get(cache_key)
            if cached_result:
                try:
                    # Return the cached result
                    return pickle.loads(cached_result)
                except Exception:
                    # Log error and proceed with the function call
                    pass

            # Call the function and cache the result
            result = await func(*args, **kwargs)

            # Only cache successful results
            if result:  # Don't cache empty results
                try:
                    redis.set(cache_key, pickle.dumps(result), ex=ttl)
                except Exception:
                    # If caching fails, just return the result
                    pass

            return result

        return wrapper

    return decorator


def invalidate_publication_cache(publication_workspace_id: str):
    """
    Invalidate Redis cache entries related to a specific publication workspace ID.

    Args:
        publication_workspace_id: The ID of the publication workspace to invalidate
    """
    redis = get_redis_client()

    # Define the specific keys to invalidate based on the simplified key structure
    keys_to_delete = [
        f"pubproc:documents:{publication_workspace_id}",
        f"pubproc:forum:{publication_workspace_id}",
        # Add other key patterns that should be invalidated for this publication
    ]

    # Delete the specific keys
    if keys_to_delete:
        redis.delete(*keys_to_delete)
