"""Dutch full-text matching and ranking over ``publications.searchable_content``.

Shared by the award tools and the publication tools so both rank the same way.

The indexed expression is spelled out with ``literal_column`` rather than built
from ``func.to_tsvector(...)`` on purpose: SQLAlchemy renders a bind parameter
for the text-search config, and Postgres will not match an expression index
whose config was a literal against a query whose config is a parameter. The
string below must stay character-identical to the index definition in migration
``c4d5e6f7a8b9``.
"""

import logging
import re
import time
from typing import List, Optional

from sqlalchemy import and_, func, literal_column, or_, text

from app.models.publication_models import Publication

logger = logging.getLogger(__name__)

# Must match idx_publications_searchable_content_fts exactly.
SEARCHABLE_TSVECTOR = literal_column(
    "to_tsvector('dutch', coalesce(publications.searchable_content, ''))"
)

_DUTCH = literal_column("'dutch'")

# Below this length a term is more likely a reference fragment than a word, and
# websearch_to_tsquery will usually reduce it to nothing.
_MIN_TSQUERY_LENGTH = 3


# Recall beats precision for this workload. websearch_to_tsquery ANDs its terms,
# so "dakrenovatie schoolgebouw" matches only documents containing both words --
# and the retrieval agent seeds its candidate pool with an entire tender title,
# which would then match almost nothing. Matching ANY term and letting ts_rank_cd
# order the results degrades gracefully instead of returning an empty set.
#
# Each term is passed as a separate bind parameter rather than assembled into a
# to_tsquery string, so no escaping is required and a stray ':' or '&' in a title
# cannot produce a syntax error.
MAX_QUERY_TERMS = 8

# The trigram index backing the substring arm. It only exists where the server
# has pg_trgm, which is not everywhere -- see migration c4d5e6f7a8b9.
TRGM_INDEX_NAME = "idx_publications_searchable_content_trgm"

_substring_arm_indexed: Optional[bool] = None
_substring_arm_checked_at: float = 0.0

# How long to wait before re-probing after a negative answer. A positive answer
# is cached for the life of the process -- the index is not going to disappear --
# but a negative one should not be permanent: installing pg_trgm and building the
# index is exactly the fix for a missing index, and it should take effect without
# needing a rollout.
_ABSENT_RECHECK_SECONDS = 300.0


def substring_arm_is_indexed() -> bool:
    """Whether the trigram index exists, so the ILIKE arm is affordable.

    ORing an unindexed ILIKE next to the tsvector match does not merely cost the
    ILIKE's own time -- it drags the whole disjunction onto a sequential scan.
    Measured against production (107k publications, no pg_trgm, so no trigram
    index): the FTS arm alone answers in 0.01s, the ILIKE arm alone in 3.3s, and
    the two ORed together in 19.7s for one term, timing out at the 30s
    statement_timeout as soon as there are two.

    So the arm is included only when its index is there. Without it, search
    loses the substring matches tsquery cannot produce -- partial words, and
    reference numbers that tokenise away -- which is a real loss of recall, but
    a smaller one than every multi-word search failing.

    A positive answer is cached for the life of the process. A negative one is
    re-probed every _ABSENT_RECHECK_SECONDS, so building the index takes effect
    without a rollout. A failed check is not cached at all, and counts as "not
    indexed" so a probe that cannot run never produces the slow query.
    """
    global _substring_arm_indexed, _substring_arm_checked_at
    if _substring_arm_indexed:
        return True
    if (
        _substring_arm_indexed is not None
        and time.monotonic() - _substring_arm_checked_at < _ABSENT_RECHECK_SECONDS
    ):
        return False

    from app.config.postgres import engine

    try:
        with engine.connect() as connection:
            found = bool(
                connection.execute(
                    text("SELECT 1 FROM pg_class WHERE relname = :name"),
                    {"name": TRGM_INDEX_NAME},
                ).scalar()
            )
    except Exception as exc:
        logger.warning("Could not check for %s: %s", TRGM_INDEX_NAME, exc)
        return False

    if not found and _substring_arm_indexed is None:
        logger.warning(
            "%s is missing, so substring matching is disabled for full-text "
            "search; queries fall back to the tsvector arm only. Re-checking "
            "every %.0fs.",
            TRGM_INDEX_NAME,
            _ABSENT_RECHECK_SECONDS,
        )
    if found and _substring_arm_indexed is False:
        logger.info("%s is now present; substring matching re-enabled.", TRGM_INDEX_NAME)

    _substring_arm_indexed = found
    _substring_arm_checked_at = time.monotonic()
    return found


def _terms(term: str) -> List[str]:
    """Split a query into distinct, index-worthy words, longest first."""
    words = re.findall(r"\w+", term, flags=re.UNICODE)
    seen = set()
    out = []
    for word in words:
        lowered = word.lower()
        if len(lowered) < _MIN_TSQUERY_LENGTH or lowered in seen:
            continue
        seen.add(lowered)
        out.append(word)
    # Longer words carry more signal; keep those when truncating.
    out.sort(key=len, reverse=True)
    return out[:MAX_QUERY_TERMS]


def _has_explicit_syntax(term: str) -> bool:
    """A quoted phrase or an explicit operator means the caller meant it."""
    return '"' in term or " OR " in term or " -" in term


def _tsquery(term: str):
    return func.websearch_to_tsquery(_DUTCH, term)


def build_fts_condition(term: Optional[str], match_all: bool = False):
    """Match a free-text query against a publication's flattened text.

    Returns None when there is nothing to match, so callers can skip the filter.

    By default any term may match. Pass match_all=True, or use websearch syntax
    ("quoted phrase", OR, -excluded), to require all of them.

    The substring arm is not redundant: tsquery drops stopwords and short tokens,
    so a search for a reference number or a two-letter code would otherwise
    return nothing at all. It is only included when the trigram index exists to
    keep it off a sequential scan -- see substring_arm_is_indexed().
    """
    if not term or not term.strip():
        return None

    cleaned = term.strip()
    substring = Publication.searchable_content.ilike(f"%{cleaned}%")
    indexed = substring_arm_is_indexed()

    if len(cleaned) < _MIN_TSQUERY_LENGTH:
        # Too short to tokenise, so the substring arm is the only thing that can
        # match at all. Returned even unindexed: one sequential scan beats
        # answering nothing.
        return substring

    if match_all or _has_explicit_syntax(cleaned):
        exact = SEARCHABLE_TSVECTOR.op("@@")(_tsquery(cleaned))
        return or_(exact, substring) if indexed else exact

    terms = _terms(cleaned)
    if not terms:
        return substring

    arms = [SEARCHABLE_TSVECTOR.op("@@")(_tsquery(word)) for word in terms]
    if indexed:
        arms.append(substring)
    return or_(*arms) if len(arms) > 1 else arms[0]


def build_fts_rank(term: Optional[str], match_all: bool = False):
    """Relevance expression for ordering, or None when there is no query.

    ts_rank_cd is cover-density ranking: it rewards matches that sit close
    together, which for tender text is a decent proxy for "about the same thing"
    rather than "these words both happen to appear". Per-term ranks are summed,
    so a document matching more of the query outranks one matching less.
    """
    if not term or not term.strip():
        return None

    cleaned = term.strip()
    if len(cleaned) < _MIN_TSQUERY_LENGTH:
        return None

    if match_all or _has_explicit_syntax(cleaned):
        return func.ts_rank_cd(SEARCHABLE_TSVECTOR, _tsquery(cleaned))

    terms = _terms(cleaned)
    if not terms:
        return None

    rank = func.ts_rank_cd(SEARCHABLE_TSVECTOR, _tsquery(terms[0]))
    for word in terms[1:]:
        rank = rank + func.ts_rank_cd(SEARCHABLE_TSVECTOR, _tsquery(word))
    return rank


def build_region_condition(regions: Optional[List[str]]):
    """Match any of the given NUTS codes, including their descendants.

    NUTS is hierarchical, so filtering on "BE2" (Vlaanderen) has to match
    "BE211", "BE212" and so on. Publication.nuts_codes is an array, hence the
    unnest-and-prefix form rather than a plain overlap.
    """
    if not regions:
        return None

    prefixes = [r.strip().upper() for r in regions if r and r.strip()]
    if not prefixes:
        return None

    conditions = []
    for prefix in prefixes:
        conditions.append(
            func.array_to_string(Publication.nuts_codes, ",").ilike(f"%{prefix}%")
        )
    return or_(*conditions)


def build_value_condition(
    min_value: Optional[float], max_value: Optional[float], column
):
    """Bound a value column, ignoring rows where the value is missing or zero.

    A great many awards carry no published amount; treating those as 0 would put
    them all inside any range starting at 0, which is worse than excluding them.
    """
    conditions = []
    if min_value is not None:
        conditions.append(and_(column.isnot(None), column >= min_value))
    if max_value is not None:
        conditions.append(and_(column.isnot(None), column <= max_value))

    if not conditions:
        return None
    return and_(*conditions)
