"""Bring the database up to date at startup.

Two paths, because the two situations are genuinely different:

* **An existing database** takes the normal ``alembic upgrade head``.

* **An empty database** is created from the models and stamped at head. This
  exists because the initial revision (``8a03694dc199``) is an empty ``pass``
  and nothing else ever created the tables -- so ``alembic upgrade head`` against
  a fresh database used to run every revision against tables that did not exist
  and fail on the first ``ALTER TABLE``. Provisioning a new environment was
  impossible; the schema had only ever been created out of band.

Rewriting that initial revision after the fact would mean hand-writing the
historical DDL and hoping it matches what production actually has. Creating a
fresh database from the models is both safer and verifiable, and it cannot
affect an existing deployment: production is not empty, so it takes the upgrade
path exactly as before.
"""

import logging

import alembic.config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Presence of this table is the test for "has this database ever been set up".
# Deliberately not alembic_version: a database can carry a stamp with no tables
# (running the old no-op initial revision did exactly that).
SENTINEL_TABLE = "publications"

# Declared on the model, but it needs the pg_trgm operator class to exist.
TRGM_INDEX_NAME = "idx_publications_searchable_content_trgm"

# Serialises migrations across replicas. The API runs 3-7 pods and every one of
# them calls run_migration() on start, so without this they race -- and the
# indexes are now built with CREATE INDEX CONCURRENTLY, where losing that race
# can leave an index behind marked invalid and permanently unused.
#
# An arbitrary but stable key; advisory locks share one namespace per database.
MIGRATION_LOCK_KEY = 0x70726F63  # "proc"

# How long a pod waits for whichever replica got there first. Comfortably longer
# than a migration should take, short enough not to hold up a rollout.
MIGRATION_LOCK_TIMEOUT_MS = 120_000
MIGRATION_LOCK_TIMEOUT = f"{MIGRATION_LOCK_TIMEOUT_MS}ms"


def _lock_engine():
    """A dedicated engine for the advisory lock, separate from the app pool.

    Two reasons not to borrow app.config.postgres.engine here:

    * It is created with ``-c statement_timeout=30000``. statement_timeout is
      what actually cancels a waiting ``pg_advisory_lock()``, so on the shared
      engine the wait ended at 30s no matter what lock_timeout said -- the 120s
      above was dead code.
    * Raising the timeout with ``SET`` would fix that but leak: the connection
      goes back to the pool carrying the new setting, so ordinary request
      queries would inherit a 120s statement_timeout instead of 30s.

    NullPool because this connection is opened once per process start.
    """
    from app.config.settings import settings

    return create_engine(
        settings.postgres_con_url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 10,
            "options": (
                f"-c statement_timeout={MIGRATION_LOCK_TIMEOUT_MS} "
                f"-c lock_timeout={MIGRATION_LOCK_TIMEOUT_MS}"
            ),
        },
    )


def _database_is_empty() -> bool:
    from app.config.postgres import engine

    try:
        return not inspect(engine).has_table(SENTINEL_TABLE)
    except Exception as exc:
        # If the check itself fails, assume an existing database and let the
        # normal upgrade path report the real problem.
        logger.warning("Could not inspect the database, assuming it exists: %s", exc)
        return False


def _create_from_models() -> None:
    from app.config.postgres import engine
    from app.models.base import Base

    # Imported for their side effect: a model class has to be imported before it
    # appears in Base.metadata, and create_all only creates what it can see.
    import app.models.company_award_models  # noqa: F401
    import app.models.company_models  # noqa: F401
    import app.models.conversation_models  # noqa: F401
    import app.models.email_models  # noqa: F401
    import app.models.kanban_models  # noqa: F401
    import app.models.notification_models  # noqa: F401
    import app.models.publication_contract_models  # noqa: F401
    import app.models.publication_models  # noqa: F401

    _prepare_pg_trgm(Base)

    Base.metadata.create_all(engine)


def _prepare_pg_trgm(Base) -> None:
    """Create pg_trgm for the fresh-database path, or drop the index needing it.

    Mirrors the guard in migration c4d5e6f7a8b9: pg_trgm lives in
    postgresql-contrib and is not installed everywhere. gin_trgm_ops does not
    exist without it, so leaving the index declared would make create_all fail
    outright rather than merely produce a slower substring search.
    """
    from app.config.postgres import engine

    with engine.begin() as connection:
        available = connection.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm'")
        ).scalar()
        if available:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            return

    logger.warning(
        "pg_trgm is not available on this server; skipping %s. The substring arm "
        "of search still returns the same rows, but from a sequential scan.",
        TRGM_INDEX_NAME,
    )
    table = Base.metadata.tables["publications"]
    table.indexes = {ix for ix in table.indexes if ix.name != TRGM_INDEX_NAME}


def _migrate():
    if _database_is_empty():
        logger.info("Empty database detected; creating schema from models.")
        _create_from_models()
        alembic.config.main(argv=["--raiseerr", "stamp", "head"])
        logger.info("Schema created and stamped at head.")
        return

    alembic.config.main(argv=["--raiseerr", "upgrade", "head"])


def run_migration():
    """Migrate, holding an advisory lock so only one replica does it at a time.

    The lock is session-scoped and released on the connection below, or by the
    server if this pod dies mid-migration -- so a crashed pod cannot wedge a
    rollout.
    """
    engine = _lock_engine()
    connection = engine.connect()
    try:
        try:
            connection.execute(
                text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
            )
        except Exception as exc:
            # Another replica has been migrating for longer than the timeout.
            # It is the one holding the lock, so it is the one that will finish;
            # starting a competing run would be worse than waiting for the next
            # pod restart.
            logger.warning(
                "Could not acquire the migration lock within %s (%s); "
                "another instance is migrating. Skipping.",
                MIGRATION_LOCK_TIMEOUT,
                exc,
            )
            return

        try:
            _migrate()
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY}
            )
            connection.commit()
    finally:
        connection.close()
        engine.dispose()
