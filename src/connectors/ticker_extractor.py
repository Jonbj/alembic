"""Maps GDELT organisation names to ticker symbols via PostgreSQL lookup."""

import re

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
        """Return deduplicated list of tickers for the given org names."""
        if not org_names:
            return []

        normalized = list({self.normalize(n) for n in org_names if self.normalize(n)})
        if not normalized:
            return []

        tickers: list[str] = []
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ticker FROM ticker_lookup WHERE lower(company_name) = ANY(%s)",
                (normalized,),
            )
            tickers.extend(row[0] for row in cur.fetchall())

            original_stripped = [n.strip() for n in org_names if n.strip()]
            if original_stripped:
                cur.execute(
                    "SELECT DISTINCT ticker FROM ticker_lookup WHERE aliases && %s::text[]",
                    (original_stripped,),
                )
                for row in cur.fetchall():
                    if row[0] not in tickers:
                        tickers.append(row[0])

        return list(dict.fromkeys(tickers))

    @staticmethod
    def normalize(name: str) -> str:
        """Lowercase, strip corporate suffixes and punctuation."""
        cleaned = _SUFFIX_RE.sub("", name.strip())
        cleaned = re.sub(r"[,.]", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip().lower()
