import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import Settings

settings = Settings()


class SemanticSearchEngine:
    """Handle semantic search operations using pgai vectorizer."""

    @staticmethod
    async def hybrid_search_publications(
        session: Session,
        query: str,
        limit: int = 100,
        similarity_threshold: float = 0.7,
        company_vat_number: Optional[str] = None,
        region_filter: Optional[List[str]] = None,
        sector_filter: Optional[List[str]] = None,
        active_only: bool = True,
    ) -> List[Tuple[str, float, Dict[str, any]]]:
        """
        Perform hybrid search combining semantic similarity and keyword matching.

        Args:
            session: Database session
            query: Search query text
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
            company_vat_number: Optional company VAT for personalized results # TODO: not implemented
            region_filter: Optional NUTS codes filter
            sector_filter: Optional CPV sector filter
            active_only: Only return active publications

        Returns:
            List of tuples (publication_workspace_id, combined_score)
        """
        try:
            # Build the semantic search query using pgai
            semantic_query = text(
                """
                WITH semantic_results AS (
                    SELECT DISTINCT ON (pe.publication_workspace_id)
                        pe.publication_workspace_id,
                        1 - (pe.embedding <=> ai.openai_embed(
                            'text-embedding-3-small', 
                            :query,
                            api_key => :api_key
                        )::vector) as similarity_score,
                        pe.chunk as matching_chunk,
                        p.publication_date,
                        p.vault_submission_deadline,
                        p.cpv_main_code_code,
                        p.nuts_codes,
                        p.estimated_value
                    FROM publications_embeddings pe
                    JOIN publications p ON p.publication_workspace_id = pe.publication_workspace_id
                    WHERE 1=1
                        AND (:active_only = false OR p.vault_submission_deadline > NOW())
                        AND 1 - (pe.embedding <=> ai.openai_embed(
                            'text-embedding-3-small', 
                            :query,
                            api_key => :api_key
                        )::vector) >= :similarity_threshold
                    ORDER BY pe.publication_workspace_id, similarity_score DESC
                ),
                keyword_results AS (
                    SELECT 
                        p.publication_workspace_id,
                        ts_rank_cd(
                            to_tsvector('dutch', p.searchable_content),
                            websearch_to_tsquery('dutch', :query)
                        ) as keyword_score
                    FROM publications p
                    WHERE to_tsvector('dutch', p.searchable_content) @@ websearch_to_tsquery('dutch', :query)
                        AND (:active_only = false OR p.vault_submission_deadline > NOW())
                )
                SELECT 
                    COALESCE(s.publication_workspace_id, k.publication_workspace_id) as publication_workspace_id,
                    COALESCE(s.similarity_score, 0) * 0.7 + COALESCE(k.keyword_score, 0) * 0.3 as combined_score,
                    s.similarity_score,
                    k.keyword_score,
                    s.matching_chunk,
                    s.publication_date,
                    s.vault_submission_deadline,
                    s.cpv_main_code_code,
                    s.nuts_codes,
                    s.estimated_value
                FROM semantic_results s
                FULL OUTER JOIN keyword_results k 
                    ON s.publication_workspace_id = k.publication_workspace_id
                WHERE COALESCE(s.similarity_score, 0) * 0.7 + COALESCE(k.keyword_score, 0) * 0.3 > 0
                ORDER BY combined_score DESC
                LIMIT :limit
            """
            )

            # Execute the query
            results = session.execute(
                semantic_query,
                {
                    "query": query,
                    "api_key": settings.openai_api_key,
                    "similarity_threshold": similarity_threshold,
                    "active_only": active_only,
                    "limit": limit,
                },
            ).fetchall()

            # Apply additional filters if needed
            filtered_results = []
            for row in results:
                # Check region filter
                if region_filter and row.nuts_codes:
                    if not any(region in row.nuts_codes for region in region_filter):
                        continue

                # Check sector filter
                if sector_filter and row.cpv_main_code_code:
                    sector_match = False
                    for sector in sector_filter:
                        if row.cpv_main_code_code.startswith(sector[:2]):
                            sector_match = True
                            break
                    if not sector_match:
                        continue

                filtered_results.append(
                    (
                        row.publication_workspace_id,
                        row.combined_score,
                        {
                            "similarity_score": row.similarity_score,
                            "keyword_score": row.keyword_score,
                            "matching_chunk": row.matching_chunk,
                        },
                    )
                )

            return filtered_results

        except Exception as e:
            logging.error(f"Error in semantic search: {e}")
            # Fall back to empty results on error
            return []

    @staticmethod
    async def explain_match(
        session: Session, publication_workspace_id: str, query: str
    ) -> Optional[str]:
        """
        Get the most relevant chunk that matches the search query.
        This helps explain why a publication was returned.
        """
        try:
            query = text(
                """
                SELECT 
                    chunk,
                    1 - (embedding <=> ai.openai_embed(
                        'text-embedding-3-small', 
                        :query,
                        api_key => :api_key
                    )::vector) as similarity_score
                FROM publications_embeddings
                WHERE publication_workspace_id = :pub_id
                ORDER BY similarity_score DESC
                LIMIT 1
            """
            )

            result = session.execute(
                query,
                {
                    "pub_id": publication_workspace_id,
                    "query": query,
                    "api_key": settings.openai_api_key,
                },
            ).fetchone()

            return result.chunk if result else None

        except Exception as e:
            logging.error(f"Error explaining match: {e}")
            return None


# Singleton instance
semantic_search = SemanticSearchEngine()
