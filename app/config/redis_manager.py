import redis
from redis.client import Redis

from app.config.settings import settings


def get_redis_client() -> Redis:
    """
    Create and return a Redis client connection with text decoding.
    Use this for non-binary data only.
    """
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=False,
    )
