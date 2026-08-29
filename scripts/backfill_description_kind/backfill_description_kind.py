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
"""

import argparse
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_

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


def backfill(commit: bool = False, sample: int = 8) -> None:
    changed = ambiguous = 0
    samples = []

    with get_session() as session:
        rows = (
            session.query(Description)
            .filter(Description.kind == KIND_UNKNOWN)
            .filter(
                or_(
                    Description.dossier_reference_number.isnot(None),
                    Description.lot_id.isnot(None),
                )
            )
            .all()
        )
        logger.info("%d unclassified row(s) attached to a dossier or lot", len(rows))

        groups: Dict[Tuple, List[Description]] = defaultdict(list)
        for row in rows:
            key = (row.dossier_reference_number, row.lot_id, row.language)
            groups[key].append(row)

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
            logger.info("Committed.")
        else:
            session.rollback()
            logger.info("Dry run: nothing written. Re-run with --commit to apply.")

    verb = "reclassified" if commit else "would reclassify"
    logger.info("%s %d row(s); %d left as 'unknown' (ambiguous)", verb, changed, ambiguous)
    if samples:
        logger.info("sample of rows %s titles:", "now marked as" if commit else "that would become")
        for key, kind, text in samples:
            logger.info("   dossier=%s lot=%s lang=%s -> %r", key[0], key[1], key[2], text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Actually write the changes.")
    parser.add_argument("--sample", type=int, default=8, help="How many examples to print.")
    args = parser.parse_args()
    backfill(commit=args.commit, sample=args.sample)


if __name__ == "__main__":
    main()
