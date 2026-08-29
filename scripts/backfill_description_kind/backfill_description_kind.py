"""Classify legacy `descriptions` rows as titles or descriptions.

Rows created before migration ``d5e6f7a8b9c0`` carry kind='unknown' and belong
to both the titles and the descriptions collection -- exactly as they behaved
before the discriminator existed. Nothing is broken while they stay that way;
they are simply imprecise, so a dossier's title may render as its body text.

This script guesses. It cannot do better: the distinction was never recorded,
and the source notice is long gone. Within one parent and language it treats the
SHORTEST text as the title and the rest as descriptions, because that is what
procurement text actually looks like -- a title is a line, a description is a
paragraph.

Because it guesses, it is dry-run by default and prints what it would change.
Read the sample before passing --commit.

    python -m scripts.backfill_description_kind.backfill_description_kind
    python -m scripts.backfill_description_kind.backfill_description_kind --commit

Rows are only reclassified if the shortest text is clearly shorter than the
next one (see MIN_RATIO); ambiguous parents are left as 'unknown', which is the
safe state.

Work is done one page of parents at a time and committed per page, so the script
holds a bounded amount of memory whatever the size of the table, and is safe to
interrupt and re-run: a committed page is no longer 'unknown', so it is not
picked up again.
"""

import argparse
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import or_, text

from app.config.postgres import get_session
from app.models.publication_models import (
    KIND_DESCRIPTION,
    KIND_TITLE,
    KIND_UNKNOWN,
    Description,
)

# Imported so SQLAlchemy can resolve relationship targets by class name.
import app.models.company_models  # noqa: F401
import app.models.conversation_models  # noqa: F401
import app.models.kanban_models  # noqa: F401
import app.models.publication_contract_models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# The shortest text must be at most this fraction of the next-shortest to be
# called a title. Two texts of similar length are not a title and a description.
MIN_RATIO = 0.6

# How many parent groups to load, classify and commit at a time. A group is a
# handful of rows, so this bounds resident memory regardless of table size --
# the previous .all() over every unclassified row measured 3.07 GB at 1.5M rows
# and grows linearly. Sized in parents rather than rows, so keep it modest: a
# parent with an unusually long list of descriptions multiplies it.
GROUP_BATCH = 500

# app.config.postgres pins statement_timeout to 30s for request traffic. The
# scans here are deliberately bounded, but the initial DISTINCT over
# descriptions is a single large aggregate and legitimately takes longer than a
# request ever should.
MAINTENANCE_STATEMENT_TIMEOUT = "600s"


def _relax_statement_timeout(session) -> None:
    session.execute(text(f"SET statement_timeout = '{MAINTENANCE_STATEMENT_TIMEOUT}'"))


def _classify(rows: List[Description]) -> Optional[List[Tuple[Description, str]]]:
    """Return (row, kind) assignments, or None when the group is ambiguous."""
    if len(rows) < 2:
        # A lone row could be either. Leaving it 'unknown' keeps it in both
        # collections, which is strictly better than guessing wrong.
        return None

    ordered = sorted(rows, key=lambda r: (len(r.text or ""), r.id))
    shortest, next_shortest = ordered[0], ordered[1]
    if len(next_shortest.text or "") == 0:
        return None
    if len(shortest.text or "") / len(next_shortest.text or "") > MIN_RATIO:
        return None

    return [(shortest, KIND_TITLE)] + [(r, KIND_DESCRIPTION) for r in ordered[1:]]


def _attached_to_a_parent():
    """The rows this script is allowed to touch."""
    return (
        Description.kind == KIND_UNKNOWN,
        or_(
            Description.dossier_reference_number.isnot(None),
            Description.lot_id.isnot(None),
        ),
    )


# The two passes the table is walked in. Paging on the parent id rather than on
# the full (dossier, lot, language) group key is deliberate: lot_id is NULL for
# every dossier-attached row, and `(a, b, c) IN ((x, NULL, z))` evaluates to
# NULL in SQL, not true -- a tuple IN over these keys silently matches nothing.
#
# Splitting on "has a dossier" vs "has only a lot" also guarantees no group is
# ever split across passes: every row in a group shares the group's
# dossier_reference_number, so whichever pass claims that value claims the whole
# group. Loading a superset of the group and regrouping in Python is what keeps
# the shortest-text rule looking at all of a parent's rows at once.
PASSES = (
    ("dossier", Description.dossier_reference_number, None),
    ("lot", Description.lot_id, Description.dossier_reference_number.is_(None)),
)


def _parent_ids(session, column, extra) -> List:
    """Distinct non-null parents that still have unclassified rows."""
    query = session.query(column).filter(
        Description.kind == KIND_UNKNOWN, column.isnot(None)
    )
    if extra is not None:
        query = query.filter(extra)
    return [row[0] for row in query.distinct().all()]


def _load_groups(session, column, extra, ids: List) -> Dict[Tuple, List[Description]]:
    """Load every unclassified row under the given parents, grouped by key."""
    query = session.query(Description).filter(
        Description.kind == KIND_UNKNOWN, column.in_(ids)
    )
    if extra is not None:
        query = query.filter(extra)

    groups: Dict[Tuple, List[Description]] = defaultdict(list)
    for row in query.all():
        groups[(row.dossier_reference_number, row.lot_id, row.language)].append(row)
    return groups


def backfill(commit: bool = False, sample: int = 8, batch: int = GROUP_BATCH) -> None:
    changed = ambiguous = 0
    samples = []

    for label, column, extra in PASSES:
        with get_session() as session:
            _relax_statement_timeout(session)
            ids = _parent_ids(session, column, extra)
        logger.info("%s pass: %d parent(s) with unclassified rows", label, len(ids))

        for start in range(0, len(ids), batch):
            page = ids[start : start + batch]
            with get_session() as session:
                _relax_statement_timeout(session)
                groups = _load_groups(session, column, extra, page)

                for key, group in groups.items():
                    assignments = _classify(group)
                    if assignments is None:
                        ambiguous += len(group)
                        continue
                    for row, kind in assignments:
                        row.kind = kind
                        changed += 1
                        if len(samples) < sample and kind == KIND_TITLE:
                            samples.append((key, kind, (row.text or "")[:70]))

                if commit:
                    session.commit()
                else:
                    session.rollback()

            logger.info(
                "%s pass: %d/%d parent(s) processed; %d row(s) reclassified so far",
                label,
                min(start + batch, len(ids)),
                len(ids),
                changed,
            )

    if commit:
        logger.info("Committed.")
    else:
        logger.info("Dry run: nothing written. Re-run with --commit to apply.")

    verb = "reclassified" if commit else "would reclassify"
    logger.info("%s %d row(s); %d left as 'unknown' (ambiguous)", verb, changed, ambiguous)
    if samples:
        logger.info("sample of rows %s titles:", "now marked as" if commit else "that would become")
        for key, kind, snippet in samples:
            logger.info("   dossier=%s lot=%s lang=%s -> %r", key[0], key[1], key[2], snippet)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Actually write the changes.")
    parser.add_argument("--sample", type=int, default=8, help="How many examples to print.")
    parser.add_argument(
        "--batch",
        type=int,
        default=GROUP_BATCH,
        help="Parent groups to load and commit at a time.",
    )
    args = parser.parse_args()
    backfill(commit=args.commit, sample=args.sample, batch=args.batch)


if __name__ == "__main__":
    main()
