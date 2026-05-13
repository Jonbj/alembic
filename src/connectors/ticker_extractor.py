"""Maps GDELT organisation names to ticker symbols via PostgreSQL lookup.

This module bridges the entity names extracted by `GDELTGKGConnector` (e.g.
"Apple Inc", "Microsoft Corporation") to actual ticker symbols ("AAPL",
"MSFT") using a PostgreSQL lookup table.

Lookup strategy (two-phase):
  1. Primary lookup — normalised `company_name` match.
     - Strip corporate suffixes (Inc, Corp, Ltd, …).
     - Lowercase and remove punctuation.
     - Query: `SELECT ticker FROM ticker_lookup WHERE lower(company_name) = ANY(...)`
  2. Fallback lookup — alias match.
     - Some organisations have historical names stored in the `aliases` array
       (e.g. "Apple Computer" → AAPL).
     - Query: `SELECT ticker FROM ticker_lookup WHERE aliases && original_names`

If both lookups fail, the article is discarded by the caller
(`NewsIngestionWorker`), which is the intended behaviour: we only queue
news for which we have a confident ticker mapping.

Performance considerations:
  - `ticker_lookup` has indexes on `lower(company_name)` and `aliases` (GIN),
    so both lookups are O(log n) or better.
  - `extract()` deduplicates tickers before returning, so an article mentioning
    the same company under two aliases produces only one ticker.
"""

import re

# Regex that strips common corporate suffixes and trailing dots.
# Compiled once at import time for performance.
_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|corporation|corp|limited|ltd|llc|company|co|plc|"
    r"group|holdings|international|intl|s\.?p\.?a|n\.?v|b\.?v)\b\.?",
    re.IGNORECASE,
)


class TickerExtractor:
    """Maps a list of GDELT organisation names to ticker symbols.

    Primary lookup: normalised company_name match (case-insensitive, suffix-stripped).
    Fallback lookup: alias array match for historical name variants.
    No match → empty list → article is discarded by caller.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def extract(self, org_names: list[str]) -> list[str]:
        """Return deduplicated list of tickers for the given org names.

        Algorithm:
          1. Normalise every org name (strip suffixes, lowercase, remove punctuation).
          2. Query `ticker_lookup` for exact normalised match (primary lookup).
          3. Query `ticker_lookup` for alias match using the *original* names
             (fallback for historical variants like "Apple Computer").
          4. Deduplicate and return ordered list.

        Args:
            org_names: List of organisation names from GDELT GKG V2Organizations.

        Returns:
            Ordered deduplicated list of ticker symbols. Empty list means
            no known company was recognised — the article should be discarded.
        """
        if not org_names:
            # Empty input → no tickers. Avoids an unnecessary DB round-trip.
            return []

        # Normalise and remove empty results.
        normalized = list({self.normalize(n) for n in org_names if self.normalize(n)})
        if not normalized:
            return []

        tickers: list[str] = []

        # Phase 1: primary lookup by normalised company_name
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ticker FROM ticker_lookup WHERE lower(company_name) = ANY(%s)",
                (normalized,),
            )
            tickers.extend(row[0] for row in cur.fetchall())

            # Phase 2: fallback lookup by alias (original names, NOT normalised,
            # because aliases are stored in their original form in the DB).
            original_stripped = [n.strip() for n in org_names if n.strip()]
            if original_stripped:
                cur.execute(
                    "SELECT DISTINCT ticker FROM ticker_lookup WHERE aliases && %s::text[]",
                    (original_stripped,),
                )
                for row in cur.fetchall():
                    if row[0] not in tickers:
                        tickers.append(row[0])

        # Preserve order while removing duplicates (dict.fromkeys idiom).
        return list(dict.fromkeys(tickers))

    @staticmethod
    def normalize(name: str) -> str:
        """Lowercase, strip corporate suffixes and punctuation.

        Steps:
          1. Strip corporate suffixes using `_SUFFIX_RE` (Inc, Corp, Ltd, …).
          2. Remove commas and dots (e.g. "Inc." → "Inc" already stripped).
          3. Collapse multiple spaces to single space.
          4. Lowercase and strip leading/trailing whitespace.

        Examples:
            "Apple Inc"           → "apple"
            "Microsoft Corp."     → "microsoft"
            "Johnson & Johnson"   → "johnson & johnson"
            "3M Co"               → "3m"

        Args:
            name: Raw organisation name from GDELT.

        Returns:
            Normalised string suitable for case-insensitive exact matching.
        """
        cleaned = _SUFFIX_RE.sub("", name.strip())
        cleaned = re.sub(r"[,.]", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip().lower()
