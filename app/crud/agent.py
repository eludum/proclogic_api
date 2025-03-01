from typing import Dict, Optional, List

from app.config.redis_manager import get_redis_client
from app.config.settings import Settings

settings = Settings()


# agent_storage.py
class RedisAgentStorage:
    """
    Class to handle storing agent data in Redis.
    """

    def __init__(self):
        self.redis = get_redis_client()
        self.ttl = settings.redis_agent_ttl

    def store_company_assistant(self, vat_number: str, assistant_id: str) -> None:
        """
        Store a company's assistant ID in Redis.
        """
        self.redis.set(f"company:{vat_number}:assistant_id", assistant_id, ex=self.ttl)

    def get_company_assistant_id(self, vat_number: str) -> Optional[str]:
        """
        Get a company's assistant ID from Redis.
        """
        return self.redis.get(f"company:{vat_number}:assistant_id")

    def store_publication_data(
        self, vat_number: str, publication_id: str, vector_store_id: str, thread_id: str
    ) -> None:
        """
        Store publication data for a company.
        """
        # Store as a hash
        publication_key = f"company:{vat_number}:publication:{publication_id}"
        self.redis.hset(
            publication_key,
            mapping={
                "vector_store_id": vector_store_id,
                "thread_id": thread_id,
            },
        )
        self.redis.expire(publication_key, self.ttl)

        # Also keep track of active publications for a company
        self.redis.sadd(f"company:{vat_number}:active_publications", publication_id)
        self.redis.expire(f"company:{vat_number}:active_publications", self.ttl)

    def get_publication_data(
        self, vat_number: str, publication_id: str
    ) -> Optional[Dict[str, str]]:
        """
        Get publication data for a company and publication.
        """
        publication_key = f"company:{vat_number}:publication:{publication_id}"
        data = self.redis.hgetall(publication_key)
        return data if data else None

    def get_active_publications(self, vat_number: str) -> List[str]:
        """
        Get a list of active publications for a company.
        """
        return list(self.redis.smembers(f"company:{vat_number}:active_publications"))

    def delete_publication_data(self, vat_number: str, publication_id: str) -> None:
        """
        Delete publication data for a company.
        """
        # Remove the publication data
        self.redis.delete(f"company:{vat_number}:publication:{publication_id}")

        # Remove from active publications
        self.redis.srem(f"company:{vat_number}:active_publications", publication_id)

    def delete_company_data(self, vat_number: str) -> None:
        """
        Delete all data for a company.
        """
        # First get the list of active publications
        active_publications = self.get_active_publications(vat_number)

        # Delete each publication's data
        for publication_id in active_publications:
            self.delete_publication_data(vat_number, publication_id)

        # Delete the active publications set
        self.redis.delete(f"company:{vat_number}:active_publications")

        # Delete the assistant ID
        self.redis.delete(f"company:{vat_number}:assistant_id")

    def company_exists(self, vat_number: str) -> bool:
        """
        Check if a company exists in Redis.
        """
        return self.redis.exists(f"company:{vat_number}:assistant_id") > 0

    def publication_exists(self, vat_number: str, publication_id: str) -> bool:
        """
        Check if a publication exists for a company.
        """
        return (
            self.redis.exists(f"company:{vat_number}:publication:{publication_id}") > 0
        )

    def refresh_ttl(
        self, vat_number: str, publication_id: Optional[str] = None
    ) -> None:
        """
        Refresh TTL for company data and optionally for a specific publication.
        """
        # Refresh company assistant TTL
        self.redis.expire(f"company:{vat_number}:assistant_id", self.ttl)
        self.redis.expire(f"company:{vat_number}:active_publications", self.ttl)

        # If publication ID is provided, refresh that publication's TTL
        if publication_id:
            self.redis.expire(
                f"company:{vat_number}:publication:{publication_id}", self.ttl
            )
