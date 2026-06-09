"""Zeygos sector report PDF parser.

Extracts per-ticker scores from the Zeygos "Selezione Top 5 Titoli per Settore"
PDF reports and returns a list of ZeygosRow dataclasses ready for DB insertion.

Approach: pdfplumber table extraction (deterministic, no hallucination risk).
Each bordered table is matched to its sector header by finding the last sector
name that appears in the page text above the table bounding box.

Refinitiv ticker normalization:
  - US suffixes (.N, .OQ, .K, .OB) are stripped  → "NEM.N" → "NEM"
  - EU suffixes (.L, .PA, .MI, …) are kept intact → "GLEN.L" stays "GLEN.L"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pdfplumber


class ZeygosParseError(ValueError):
    pass


_SECTOR_NAMES = [
    "Academic & Educational Services",
    "Basic Materials",
    "Consumer Cyclicals",
    "Consumer Non-Cyclicals",
    "Energy",
    "Financials",
    "Healthcare",
    "Industrials",
    "Real Estate",
    "Technology",
    "Utilities",
]

_US_SUFFIXES  = (".N", ".OQ", ".OB", ".K", ".O")
_EU_SUFFIXES  = (".L", ".PA", ".MI", ".DE", ".AS", ".OL", ".BR", ".MC",
                 ".S", ".ST", ".HE", ".CO", ".VX", ".OL")

_ITALIAN_MONTHS = {
    "Gennaio": 1, "Febbraio": 2, "Marzo": 3, "Aprile": 4,
    "Maggio": 5, "Giugno": 6, "Luglio": 7, "Agosto": 8,
    "Settembre": 9, "Ottobre": 10, "Novembre": 11, "Dicembre": 12,
}

_MIN_ROWS = 10  # sanity floor — fewer means layout changed


@dataclass
class ZeygosRow:
    report_date:      date
    market:           str   # "USA" or "EU"
    sector:           str
    rank:             int   # 1–5 within sector
    ticker_refinitiv: str   # raw PDF value, e.g. "NEM.N"
    ticker:           str   # Alpaca-ready, e.g. "NEM" or "GLEN.L"
    company_name:     str
    score_analysts:   float
    score_momentum:   float
    score_valuation:  float
    score_solidity:   float
    score_dividend:   float
    score_growth:     float
    score_interest:   float
    score_finale:     float


def normalize_ticker(raw: str) -> str:
    """Strip US exchange suffixes; keep EU suffixes intact."""
    for suffix in _US_SUFFIXES:
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    return raw


def _parse_report_date(text: str) -> date:
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
    if not m:
        raise ZeygosParseError(f"Cannot find date in page text: {text[:120]!r}")
    day, month_it, year = int(m.group(1)), m.group(2), int(m.group(3))
    month = _ITALIAN_MONTHS.get(month_it)
    if not month:
        raise ZeygosParseError(f"Unknown Italian month name: {month_it!r}")
    return date(year, month, day)


def _parse_float(val: object) -> float:
    try:
        return float(str(val).strip().replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _is_header_row(row: list) -> bool:
    return bool(row) and str(row[0] or "").strip().lower() in ("ticker", "")


def _find_sector_above(text_above: str) -> str | None:
    """Return the sector name whose last occurrence is closest above the table."""
    best_pos = -1
    best_sector = None
    for sector in _SECTOR_NAMES:
        pos = text_above.rfind(sector)
        if pos > best_pos:
            best_pos = pos
            best_sector = sector
    return best_sector


def parse_zeygos_pdf(pdf_bytes: bytes) -> list[ZeygosRow]:
    """Parse a Zeygos PDF report and return all ZeygosRow records.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        List of ZeygosRow (one per ticker per sector).

    Raises:
        ZeygosParseError: If date extraction fails or too few rows are found.
    """
    results: list[ZeygosRow] = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        page1_text = pdf.pages[0].extract_text() or ""
        report_date = _parse_report_date(page1_text)

        # Pre-scan: find the page index and y-coordinate of "Mercato Europeo" heading.
        # We need this for per-table market assignment when the heading and a USA table
        # share the same page (market switch happens mid-page).
        eu_page_idx: int | None = None
        eu_heading_y: float = 0.0
        for idx, page in enumerate(pdf.pages):
            if "Mercato Europeo" in (page.extract_text() or ""):
                eu_page_idx = idx
                for word in page.extract_words():
                    if "Europeo" in word["text"]:
                        eu_heading_y = float(word["top"])
                        break
                break

        for page_idx, page in enumerate(pdf.pages):
            tables = page.find_tables()
            for table_obj in sorted(tables, key=lambda t: t.bbox[1]):
                table_top = table_obj.bbox[1]

                # Per-table market: compare table position against EU heading position
                if eu_page_idx is None or page_idx < eu_page_idx:
                    market = "USA"
                elif page_idx > eu_page_idx:
                    market = "EU"
                else:
                    market = "EU" if table_top > eu_heading_y else "USA"

                # Text strictly above this table on the same page → sector detection
                cropped = page.crop((0, 0, page.width, table_top))
                text_above = cropped.extract_text() or ""

                sector = _find_sector_above(text_above)
                if not sector:
                    continue

                rows = table_obj.extract()
                if not rows or len(rows) < 2:
                    continue

                data_rows = [r for r in rows if not _is_header_row(r) and r and r[0]]
                for rank, row in enumerate(data_rows, start=1):
                    if len(row) < 9:
                        continue

                    ticker_raw = str(row[0] or "").strip()
                    company   = str(row[1] or "").strip()

                    if not ticker_raw or ticker_raw.lower() == "ticker":
                        continue

                    try:
                        scores = [_parse_float(row[i]) for i in range(2, 9)]
                        # Score Finale may be in col 9 or last col if merged cells
                        score_finale = _parse_float(
                            row[9] if len(row) > 9 else row[-1]
                        )
                    except Exception:
                        continue

                    results.append(ZeygosRow(
                        report_date      = report_date,
                        market           = market,
                        sector           = sector,
                        rank             = rank,
                        ticker_refinitiv = ticker_raw,
                        ticker           = normalize_ticker(ticker_raw),
                        company_name     = company,
                        score_analysts   = scores[0],
                        score_momentum   = scores[1],
                        score_valuation  = scores[2],
                        score_solidity   = scores[3],
                        score_dividend   = scores[4],
                        score_growth     = scores[5],
                        score_interest   = scores[6],
                        score_finale     = score_finale,
                    ))

    # Deduplicate: same ticker can appear if a sector table straddles a page boundary
    seen: set[tuple] = set()
    deduped: list[ZeygosRow] = []
    for r in results:
        key = (r.report_date, r.ticker_refinitiv)
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if len(deduped) < _MIN_ROWS:
        raise ZeygosParseError(
            f"Only {len(deduped)} rows extracted (expected >= {_MIN_ROWS}). "
            "PDF layout may have changed."
        )

    return deduped
