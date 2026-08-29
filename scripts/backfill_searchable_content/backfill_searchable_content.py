"""Populate publications.searchable_content for rows that predate the column.

New and updated publications get their searchable_content written by
``get_or_create_publication``. Everything already in the database when migration
``c4d5e6f7a8b9`` ran has a NULL, and a NULL is invisible to full-text search --
which means every historical gunning would be missing from exactly the searches
this feature exists to serve.

Run once after the migration:

    python -m scripts.backfill_searchable_content.backfill_searchable_content

It is safe to re-run and safe to interrupt: work is committed in batches and
``--only-missing`` (the default) skips rows that already have content.
"""

import argparse
import logging
import time
from typing import List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import joinedload, subqueryload

from app.config.postgres import get_session
from app.models.publication_contract_models import Contract
from app.models.publication_models import Dossier, Lot, Organisation, Publication
from app.util.publication_utils.searchable import build_searchable_content

# Imported for their side effect only. SQLAlchemy resolves relationship targets
# by class name at mapper-configuration time, and CompanyPublicationMatch (in
# publication_models) points at Company. Without these, the first query raises
# "expression 'Company' failed to locate a name".
import app.models.company_models  # noqa: F401
import app.models.conversation_models  # noqa: F401
import app.models.kanban_models  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200

# app.config.postgres pins statement_timeout to 30s for request traffic. The
# per-batch work is far below that, but the initial COUNT over publications is a
# single full scan and legitimately takes longer than a request ever should.
MAINTENANCE_STATEMENT_TIMEOUT = "600s"


def _relax_statement_timeout(session) -> None:
    session.execute(text(f"SET statement_timeout = '{MAINTENANCE_STATEMENT_TIMEOUT}'"))


def _load_batch(
    session,
    offset: int,
    batch_size: int,
    only_missing: bool,
    skip: Optional[set] = None,
) -> List[Publication]:
    query = session.query(Publication)
    if only_missing:
        query = query.filter(Publication.searchable_content.is_(None))
    # Rows that failed and would otherwise be reloaded forever: with
    # only_missing the window stays at offset 0 and selects on IS NULL, so a row
    # that cannot be written is returned by every subsequent batch.
    if skip:
        query = query.filter(Publication.publication_workspace_id.notin_(skip))

    return (
        query.options(
            joinedload(Publication.dossier).subqueryload(Dossier.titles),
            joinedload(Publication.dossier).subqueryload(Dossier.descriptions),
            joinedload(Publication.organisation).subqueryload(
                Organisation.organisation_names
            ),
            subqueryload(Publication.lots).subqueryload(Lot.titles),
            subqueryload(Publication.lots).subqueryload(Lot.descriptions),
            joinedload(Publication.cpv_main_code),
            joinedload(Publication.contract).joinedload(Contract.winning_publisher),
            joinedload(Publication.contract).joinedload(Contract.contracting_authority),
            joinedload(Publication.contract).joinedload(Contract.service_provider),
        )
        # Ordering by the primary key keeps the offset walk stable across
        # batches; without it Postgres may return overlapping pages.
        .order_by(Publication.publication_workspace_id)
        .offset(offset)
        .limit(batch_size)
        .all()
    )


def backfill(batch_size: int = BATCH_SIZE, limit: Optional[int] = None, only_missing: bool = True) -> None:
    started = time.time()
    processed = 0
    written = 0
    offset = 0
    skip: set = set()

    with get_session() as session:
        _relax_statement_timeout(session)
        total_query = session.query(func.count(Publication.publication_workspace_id))
        if only_missing:
            total_query = total_query.filter(Publication.searchable_content.is_(None))
        total = total_query.scalar() or 0
        logger.info("Backfilling %d publication(s)", total if limit is None else min(total, limit))

    while True:
        if limit is not None and processed >= limit:
            break

        size = batch_size
        if limit is not None:
            size = min(batch_size, limit - processed)

        with get_session() as session:
            _relax_statement_timeout(session)
            # With only_missing the filtered set shrinks as rows are written, so
            # the window stays at 0; without it we have to walk with an offset.
            batch = _load_batch(
                session, 0 if only_missing else offset, size, only_missing, skip
            )
            if not batch:
                break

            for publication in batch:
                try:
                    content = build_searchable_content(publication)
                except Exception as exc:
                    logger.warning(
                        "Skipping %s: %s", publication.publication_workspace_id, exc
                    )
                    skip.add(publication.publication_workspace_id)
                    continue

                if content != publication.searchable_content:
                    publication.searchable_content = content
                    written += 1

            try:
                session.commit()
            except Exception as exc:
                logger.error("Batch commit failed at offset %d: %s", offset, exc)
                session.rollback()
                # Skip past the offending batch rather than looping on it. The
                # offset bump alone is not enough: under only_missing the window
                # is pinned at 0 and the same rows come back next time, so the
                # ids have to be excluded explicitly.
                skip.update(p.publication_workspace_id for p in batch)
                offset += len(batch)
                processed += len(batch)
                continue

            processed += len(batch)
            if not only_missing:
                offset += len(batch)

        logger.info("Processed %d, written %d", processed, written)

    logger.info(
        "Done. Processed %d publication(s), wrote %d, skipped %d, in %.1fs",
        processed,
        written,
        len(skip),
        time.time() - started,
    )
    if skip:
        logger.warning(
            "%d publication(s) could not be written and were left NULL; "
            "re-run to retry them.",
            len(skip),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--limit", type=int, default=None, help="Stop after this many rows."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Rebuild every row, not just those with no content yet.",
    )
    args = parser.parse_args()

    backfill(
        batch_size=args.batch_size, limit=args.limit, only_missing=not args.all
    )


if __name__ == "__main__":
    main()
