import pytest
import json
from unittest.mock import Mock

from app.util.redis_cache import redis_cache, invalidate_publication_cache


class TestRedisIntegration:
    def test_redis_cache_decorator(self, mock_redis_client):
        """Test Redis cache decorator."""
        # Mock Redis responses
        mock_redis_client.get.return_value = None  # Cache miss
        mock_redis_client.set.return_value = True

        @redis_cache(key_prefix="test", ttl=300)
        async def test_function(param: str):
            return {"result": f"processed_{param}"}

        # First call - cache miss
        import asyncio

        result = asyncio.run(test_function("value"))

        assert result == {"result": "processed_value"}
        assert mock_redis_client.get.called
        assert mock_redis_client.set.called

    def test_cache_invalidation(self, mock_redis_client):
        """Test cache invalidation."""
        publication_id = "2024-S-123-456789"

        # Mock Redis delete
        mock_redis_client.delete.return_value = 1

        invalidate_publication_cache(publication_id)

        mock_redis_client.delete.assert_called_once()
        call_args = mock_redis_client.delete.call_args[0]
        assert f"pubproc:documents:{publication_id}" in call_args

    def test_redis_connection_failure(self, mock_redis_client):
        """Test handling Redis connection failures."""
        # Mock Redis failure
        mock_redis_client.get.side_effect = Exception("Redis connection failed")

        @redis_cache(key_prefix="test", ttl=300)
        async def test_function(param: str):
            return {"result": f"processed_{param}"}

        # Should still work even if Redis fails
        import asyncio

        result = asyncio.run(test_function("value"))

        assert result == {"result": "processed_value"}
