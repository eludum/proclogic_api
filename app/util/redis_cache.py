import pickle
from functools import wraps
from typing import Callable

from app.config.redis_manager import get_redis_client

# Cache TTL in seconds
CACHE_TTL = 24 * 60 * 60


def redis_cache(key_prefix: str, ttl: int = CACHE_TTL):
    """
    Decorator for caching async function results in Redis.

    Args:
        key_prefix: Prefix for the Redis key
        ttl: Time-to-live in seconds
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip first argument if it's 'self' or client
            skip_args = 1

            # Create a unique cache key from function arguments
            # We skip the httpx.AsyncClient argument as it's not serializable and varies
            key_parts = [key_prefix, func.__name__]

            # Add arguments after the client
            for arg in args[skip_args:]:
                key_parts.append(str(arg))

            # Add sorted keyword arguments
            if kwargs:
                for k, v in sorted(kwargs.items()):
                    key_parts.append(f"{k}:{v}")

            cache_key = ":".join(key_parts)

            # Get Redis client
            redis = get_redis_client()

            # Try to get from cache
            cached_result = redis.get(cache_key)
            if cached_result:
                try:
                    # Return the cached result
                    return pickle.loads(cached_result)
                except Exception as e:
                    # Log error and proceed with the function call
                    pass

            # Call the function and cache the result
            result = await func(*args, **kwargs)

            # Only cache successful results
            try:
                redis.set(cache_key, pickle.dumps(result), ex=ttl)
            except Exception as e:
                # If caching fails, just return the result
                pass

            return result

        return wrapper

    return decorator


def invalidate_publication_cache(publication_workspace_id: str):
    """
    Invalidate all Redis cache entries related to a specific publication workspace ID.
    This should be called when a new version of a publication is detected.

    Args:
        publication_workspace_id: The ID of the publication workspace to invalidate
    """
    redis = get_redis_client()

    # Create a pattern to match all keys related to this publication workspace
    pattern = f"*:{publication_workspace_id}:*"

    # Find all keys matching this pattern
    # Use scan_iter to avoid blocking Redis for too long
    matching_keys = []
    for key in redis.scan_iter(match=pattern):
        matching_keys.append(key)

    # Also match keys where publication ID is at the end
    pattern_end = f"*:{publication_workspace_id}"
    for key in redis.scan_iter(match=pattern_end):
        matching_keys.append(key)

    # Delete all matching keys
    if matching_keys:
        redis.delete(*matching_keys)
