import redis.asyncio as redis


def create_redis() -> redis.ConnectionPool:
    return redis.ConnectionPool.from_url("redis://localhost")
