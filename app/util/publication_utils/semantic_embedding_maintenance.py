import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from app.config.postgres import get_session
from app.config.settings import Settings

settings = Settings()


async def check_vectorizer_status():
    """Check the status of the pgai vectorizer."""
    with get_session() as session:
        try:
            result = session.execute(
                text(
                    """
                    SELECT 
                        v.id,
                        v.source_table,
                        v.target_table,
                        v.embedding_model,
                        v.last_completed_at,
                        v.last_completion_status,
                        COUNT(DISTINCT p.publication_workspace_id) as total_publications,
                        COUNT(DISTINCT e.publication_workspace_id) as embedded_publications
                    FROM ai.vectorizer v
                    CROSS JOIN publications p
                    LEFT JOIN publications_embeddings e ON e.publication_workspace_id = p.publication_workspace_id
                    WHERE v.source_table = 'publications_vectorizer'::regclass
                    GROUP BY v.id, v.source_table, v.target_table, v.embedding_model, 
                             v.last_completed_at, v.last_completion_status
                """
                )
            ).fetchone()

            if result:
                logging.info(f"Vectorizer status: {result.last_completion_status}")
                logging.info(f"Last completed: {result.last_completed_at}")
                logging.info(
                    f"Publications: {result.embedded_publications}/{result.total_publications} embedded"
                )

                # Check if we need to trigger a manual run
                if result.last_completed_at:
                    time_since_last_run = datetime.now() - result.last_completed_at
                    if time_since_last_run > timedelta(hours=1):
                        logging.warning(
                            "Vectorizer hasn't run in over an hour, triggering manual run"
                        )
                        await trigger_vectorizer_run(session)
            else:
                logging.error("Vectorizer not found!")

        except Exception as e:
            logging.error(f"Error checking vectorizer status: {e}")


async def trigger_vectorizer_run(session):
    """Manually trigger the vectorizer to run."""
    try:
        session.execute(
            text("SELECT ai.vectorizer_schedule('publications_vectorizer'::regclass);")
        )
        session.commit()
        logging.info("Triggered vectorizer run")
    except Exception as e:
        logging.error(f"Error triggering vectorizer: {e}")
        session.rollback()


async def cleanup_old_embeddings():
    """Remove embeddings for publications that are no longer active."""
    with get_session() as session:
        try:
            result = session.execute(
                text(
                    """
                    DELETE FROM publications_embeddings
                    WHERE publication_workspace_id IN (
                        SELECT e.publication_workspace_id
                        FROM publications_embeddings e
                        JOIN publications p ON p.publication_workspace_id = e.publication_workspace_id
                        WHERE p.vault_submission_deadline < NOW() - INTERVAL '30 days'
                    )
                """
                )
            )

            deleted_count = result.rowcount
            session.commit()

            if deleted_count > 0:
                logging.info(f"Cleaned up {deleted_count} old publication embeddings")

        except Exception as e:
            logging.error(f"Error cleaning up embeddings: {e}")
            session.rollback()


async def ensure_embeddings_for_active_publications():
    """Ensure all active publications have embeddings."""
    with get_session() as session:
        try:
            # Find active publications without embeddings
            result = session.execute(
                text(
                    """
                    SELECT COUNT(*) as count
                    FROM publications p
                    LEFT JOIN publications_embeddings e ON e.publication_workspace_id = p.publication_workspace_id
                    WHERE p.vault_submission_deadline > NOW()
                    AND e.publication_workspace_id IS NULL
                """
                )
            ).fetchone()

            if result and result.count > 0:
                logging.warning(
                    f"Found {result.count} active publications without embeddings"
                )
                # The vectorizer should pick these up automatically

        except Exception as e:
            logging.error(f"Error checking for missing embeddings: {e}")

# TODO: embed this into lifecycle every 5 min
# Add this to your background tasks in main.py or pubproc.py
async def maintain_embeddings():
    """Periodic task to maintain embeddings."""
    logging.info("Starting embedding maintenance service")

    while True:
        try:
            await check_vectorizer_status()
            await cleanup_old_embeddings()
            await ensure_embeddings_for_active_publications()

            # Wait 30 minutes before next check
            await asyncio.sleep(1800)

        except asyncio.CancelledError:
            logging.info("Embedding maintenance service shutting down")
            raise
        except Exception as e:
            logging.error(f"Error in embedding maintenance: {e}")
            # Wait 5 minutes before retrying
            await asyncio.sleep(300)
