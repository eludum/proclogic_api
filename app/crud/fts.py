"""Dutch full-text matching and ranking over ``publications.searchable_content``.

Shared by the award tools and the publication tools so both rank the same way.

The indexed expression is spelled out with ``literal_column`` rather than built
from ``func.to_tsvector(...)`` on purpose: SQLAlchemy renders a bind parameter
for the text-search config, and Postgres will not match an expression index
whose config was a literal against a query whose config is a parameter. The
string below must stay character-identical to the index definition in migration
``c4d5e6f7a8b9``.
"""

import re
from typing import List, Optional

from sqlalchemy import and_, func, literal_column, or_

from app.models.publication_models import Publication

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
    return nothing at all. The trigram index keeps that arm off a sequential scan.
    """
    if not term or not term.strip():
        return None

    cleaned = term.strip()
    substring = Publication.searchable_content.ilike(f"%{cleaned}%")

    if len(cleaned) < _MIN_TSQUERY_LENGTH:
        return substring

    if match_all or _has_explicit_syntax(cleaned):
        return or_(SEARCHABLE_TSVECTOR.op("@@")(_tsquery(cleaned)), substring)

    terms = _terms(cleaned)
    if not terms:
        return substring

    arms = [SEARCHABLE_TSVECTOR.op("@@")(_tsquery(word)) for word in terms]
    arms.append(substring)
    return or_(*arms)


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
