import redis
from redis.client import Redis

from app.config.settings import Settings

settings = Settings()


def get_redis_client() -> Redis:
    """
    Create and return a Redis client connection.
    """
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=settings.redis_db,
        decode_responses=True,  # Automatically decode response bytes to strings
    )
