"""Eligibilita' point-in-time a ogni ribilancio (POC S3, #84).

Ogni filtro usa solo righe <= as_of. Un security inidoneo si esclude da
quella data (esclusione locale): la cross-section sopravvive. Sotto la
breadth minima la data e' marcata insufficiente e non puo' contribuire a
un esito decision-grade.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.s3_poc.dataset import PitDataset
from src.analysis.s3_poc.manifest import S3PocManifest


@dataclass(frozen=True)
class EligibilityResult:
    as_of: pd.Timestamp
    eligible: tuple[str, ...]
    excluded_counts: dict[str, int]
    min_breadth: int

    @property
    def breadth(self) -> int:
        return len(self.eligible)

    @property
    def sufficient(self) -> bool:
        return self.breadth >= self.min_breadth


def eligible_at(ds: PitDataset, manifest: S3PocManifest, as_of: pd.Timestamp) -> EligibilityResult:
    """Valuta tutti i filtri del manifest su tutte le sedute <= as_of."""
    as_of = pd.Timestamp(as_of)
    u = manifest.universe

    close_pit = ds.close.loc[ds.close.index <= as_of]
    volume_pit = ds.volume.loc[ds.volume.index <= as_of]
    cap_pit = ds.market_cap.loc[ds.market_cap.index <= as_of]

    master = ds.security_master.copy()
    master["valid_from"] = pd.to_datetime(master["valid_from"])
    master["valid_to"] = pd.to_datetime(master["valid_to"])
    ok_type = (
        master["share_type"].isin(u.allowed_share_types)
        & master["primary_exchange"].isin(u.us_primary_exchanges)
        & (master["valid_from"] <= as_of)
        & (master["valid_to"] >= as_of)
    )

    delisted_by = {
        row.security_id for row in ds.delistings.itertuples()
        if pd.Timestamp(row.delisting_date) <= as_of
    }

    excluded: dict[str, str] = {}
    eligible: list[str] = []

    for sec in close_pit.columns:
        if sec in delisted_by:
            excluded[sec] = "delisted"
            continue
        master_row = master[master["security_id"] == sec]
        if master_row.empty or not bool(ok_type.loc[master_row.index[0]]):
            excluded[sec] = "security_type"
            continue

        prices = close_pit[sec].dropna()
        if len(prices) < u.min_history_sessions:
            excluded[sec] = "history"
            continue
        last_price = prices.iloc[-1]
        if last_price < u.min_price_usd:
            excluded[sec] = "price"
            continue

        cap_now = cap_pit[sec].iloc[-1] if sec in cap_pit.columns else float("nan")
        if not (cap_now >= u.min_market_cap_usd):
            excluded[sec] = "market_cap"
            continue

        window_prices = prices.iloc[-u.adv_window_sessions:]
        vols = volume_pit[sec].reindex(window_prices.index)
        dollar_volume = (window_prices * vols).mean()
        if not (dollar_volume >= u.min_adv_usd):
            excluded[sec] = "adv"
            continue

        eligible.append(sec)

    counts: dict[str, int] = {}
    for reason in excluded.values():
        counts[reason] = counts.get(reason, 0) + 1

    return EligibilityResult(
        as_of=as_of,
        eligible=tuple(sorted(eligible)),
        excluded_counts=counts,
        min_breadth=u.min_breadth,
    )
