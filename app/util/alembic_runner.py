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
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

# Presence of this table is the test for "has this database ever been set up".
# Deliberately not alembic_version: a database can carry a stamp with no tables
# (running the old no-op initial revision did exactly that).
SENTINEL_TABLE = "publications"

# Serialises migrations across replicas. The API runs 3-7 pods and every one of
# them calls run_migration() on start, so without this they race -- and the
# indexes are now built with CREATE INDEX CONCURRENTLY, where losing that race
# can leave an index behind marked invalid and permanently unused.
#
# An arbitrary but stable key; advisory locks share one namespace per database.
MIGRATION_LOCK_KEY = 0x70726F63  # "proc"

# How long a pod waits for whichever replica got there first. Comfortably longer
# than a migration should take, short enough not to hold up a rollout.
MIGRATION_LOCK_TIMEOUT = "120s"


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
    import app.models.company_models  # noqa: F401
    import app.models.conversation_models  # noqa: F401
    import app.models.email_models  # noqa: F401
    import app.models.kanban_models  # noqa: F401
    import app.models.notification_models  # noqa: F401
    import app.models.publication_contract_models  # noqa: F401
    import app.models.publication_models  # noqa: F401

    Base.metadata.create_all(engine)


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
    from app.config.postgres import engine

    connection = engine.connect()
    try:
        connection.execute(text(f"SET lock_timeout = '{MIGRATION_LOCK_TIMEOUT}'"))
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
