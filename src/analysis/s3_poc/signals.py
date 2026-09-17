"""Segnali delle varianti A e B del POC S3 (#84).

B (default piu' semplice): momentum totale 12-1 in log.
A (design originale): B meno beta rolling 252 sedute verso il mercato,
moltiplicato per il momentum 12-1 del mercato sulla stessa finestra.

I prezzi sono total-return come da manifest; il beta usa i rendimenti
semplici, stessa convenzione di src.strategies.s3.signal.compute_beta.
Un security senza storia sufficiente resta fuori da quel ribilancio
(esclusione locale, la cross-section non si cancella).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.s3_poc.dataset import PitDataset
from src.analysis.s3_poc.manifest import S3PocManifest

VARIANTS = ("A", "B")


def variant_signal(
    ds: PitDataset,
    manifest: S3PocManifest,
    as_of: pd.Timestamp,
    securities: tuple[str, ...],
    variant: str,
) -> dict[str, float]:
    if variant not in VARIANTS:
        raise ValueError(f"variante sconosciuta: {variant!r} (attese {VARIANTS})")
    s = manifest.signal

    as_of = pd.Timestamp(as_of)
    idx = ds.close.index.get_indexer([as_of])[0]
    if idx < 0:
        raise ValueError(f"as_of {as_of} non e' una seduta del dataset")
    i21, i252 = idx - s.skip_sessions, idx - s.lookback_sessions
    if i252 < 0:
        return {}

    close = ds.close
    market = ds.market
    mkt_mom = float(np.log(market.iloc[i21] / market.iloc[i252]))

    beta: dict[str, float] = {}
    if variant == "A":
        bw = s.beta_window_sessions
        market_ret = market.pct_change().iloc[idx - bw + 1 : idx + 1]
        m_var = float(market_ret.var())
        for sec in securities:
            ret = close[sec].pct_change().iloc[idx - bw + 1 : idx + 1]
            pair = pd.concat([ret, market_ret], axis=1, keys=["r", "m"]).dropna()
            if len(pair) < bw or m_var <= 0:
                continue
            beta[sec] = float(pair["r"].cov(pair["m"]) / m_var)

    out: dict[str, float] = {}
    for sec in securities:
        c21 = close[sec].iloc[i21] if i21 >= 0 else np.nan
        c252 = close[sec].iloc[i252]
        if pd.isna(c21) or pd.isna(c252) or c21 <= 0 or c252 <= 0:
            continue
        total = float(np.log(c21 / c252))
        if variant == "A":
            if sec not in beta:
                continue
            total -= beta[sec] * mkt_mom
        out[sec] = total
    return out
