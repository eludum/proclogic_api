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
from sqlalchemy import inspect

logger = logging.getLogger(__name__)

# Presence of this table is the test for "has this database ever been set up".
# Deliberately not alembic_version: a database can carry a stamp with no tables
# (running the old no-op initial revision did exactly that).
SENTINEL_TABLE = "publications"


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


def run_migration():
    if _database_is_empty():
        logger.info("Empty database detected; creating schema from models.")
        _create_from_models()
        alembic.config.main(argv=["--raiseerr", "stamp", "head"])
        logger.info("Schema created and stamped at head.")
        return

    alembic.config.main(argv=["--raiseerr", "upgrade", "head"])
