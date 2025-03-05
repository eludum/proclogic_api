import redis
from redis.client import Redis

from app.config.settings import Settings

settings = Settings()


def get_binary_redis_client() -> Redis:
    """
    Create and return a Redis client connection.
    
    IMPORTANT: We're not decoding responses automatically to support binary data.
    """
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=settings.redis_db,
        decode_responses=False,  # Important: Don't decode responses for binary data
    )


def get_redis_client() -> Redis:
    """
    Create and return a Redis client connection with text decoding.
    Use this for non-binary data only.
    """
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=settings.redis_db,
        decode_responses=True,
    )
