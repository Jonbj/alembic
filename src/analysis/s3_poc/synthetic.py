"""Builder del dataset sintetico PIT dorato per i test del POC S3 (#84).

Ogni security ha il proprio generatore separato, seedato da (seed, id):
aggiungere o togliere un security non cambia le serie degli altri, che e'
il prerequisito dei test di leakage (futuro che non contamina il passato).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.analysis.s3_poc.dataset import PitDataset, Provenance, canonical_sha256

_SYNTHETIC_OBTAINED_AT = date(2026, 9, 16)


@dataclass(frozen=True)
class SecuritySpec:
    security_id: str
    start_price: float = 50.0
    daily_vol: float = 0.02
    drift: float = 0.0
    volume_shares: float = 1_000_000.0
    shares_outstanding: float = 50_000_000.0
    share_type: str = "common"
    primary_exchange: str = "NYSE"
    sector: str = "TECH"
    start: date | None = None
    end: date | None = None
    delisting_date: date | None = None
    delisting_return: float = 0.0
    delisting_missing_status: bool = False
    open_unreliable_from: date | None = None


@dataclass(frozen=True)
class SyntheticSpec:
    start: date
    end: date
    securities: tuple[SecuritySpec, ...]
    market_drift: float = 0.06
    market_vol: float = 0.15
    seed: int = 84


def _security_rng(spec: SyntheticSpec, security_id: str) -> np.random.Generator:
    """Seed per-security: indipendente dagli altri security nello spec."""
    digest = hashlib.sha256(f"{spec.seed}:{security_id}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def _series_for(spec: SyntheticSpec, sec: SecuritySpec, sessions: pd.DatetimeIndex) -> pd.Series:
    rng = _security_rng(spec, sec.security_id)
    active = (sessions >= pd.Timestamp(sec.start or spec.start)) & (
        sessions <= pd.Timestamp(sec.delisting_date or sec.end or spec.end)
    )
    n = int(active.sum())
    if n == 0:
        return pd.Series(np.nan, index=sessions)
    log_ret = rng.normal(
        loc=sec.drift / 252.0,
        scale=sec.daily_vol / np.sqrt(252.0),
        size=n,
    )
    close = sec.start_price * np.exp(np.cumsum(log_ret))
    # open = media geometrica col close precedente: deterministica dai close
    prev = np.concatenate([[sec.start_price], close[:-1]])
    open_ = np.sqrt(prev * close)
    vol = sec.volume_shares * np.exp(rng.normal(0.0, 0.3, size=n))
    cap = close * sec.shares_outstanding
    reliable = np.ones(n, dtype=bool)
    if sec.open_unreliable_from is not None:
        active_dates = sessions[active]
        reliable = active_dates < pd.Timestamp(sec.open_unreliable_from)

    out = {
        "close": pd.Series(close, index=sessions[active]),
        "open": pd.Series(open_, index=sessions[active]),
        "volume": pd.Series(vol, index=sessions[active]),
        "market_cap": pd.Series(cap, index=sessions[active]),
        "open_reliable": pd.Series(reliable, index=sessions[active]).astype(bool),
    }
    return pd.DataFrame(out).reindex(sessions)


def build_synthetic_dataset(spec: SyntheticSpec) -> PitDataset:
    sessions = pd.bdate_range(spec.start, spec.end)

    market_rng = np.random.default_rng(spec.seed)
    market_log_ret = market_rng.normal(
        loc=spec.market_drift / 252.0,
        scale=spec.market_vol / np.sqrt(252.0),
        size=len(sessions),
    )
    market = pd.Series(400.0 * np.exp(np.cumsum(market_log_ret)), index=sessions)

    frames = {name: {} for name in ("close", "open", "volume", "market_cap", "open_reliable")}
    master_rows = []
    delisting_rows = []
    for sec in spec.securities:
        per_date = _series_for(spec, sec, sessions)
        for name in frames:
            frames[name][sec.security_id] = per_date[name]
        master_rows.append({
            "security_id": sec.security_id,
            "valid_from": pd.Timestamp(sec.start or spec.start),
            "valid_to": pd.Timestamp(min(
                d for d in (sec.delisting_date, sec.end, spec.end) if d is not None
            )),
            "share_type": sec.share_type,
            "primary_exchange": sec.primary_exchange,
            "sector": sec.sector,
        })
        if sec.delisting_date is not None:
            delisting_rows.append({
                "security_id": sec.security_id,
                "delisting_date": pd.Timestamp(sec.delisting_date),
                "delisting_return": float(sec.delisting_return),
                "missing_status": bool(sec.delisting_missing_status),
            })

    wide = {name: pd.DataFrame(cols).sort_index(axis=1) for name, cols in frames.items()}
    security_master = pd.DataFrame(master_rows)
    delistings = pd.DataFrame(
        delisting_rows,
        columns=["security_id", "delisting_date", "delisting_return", "missing_status"],
    )

    placeholder = Provenance(
        vendor="synthetic-golden", release="1", obtained_at=_SYNTHETIC_OBTAINED_AT,
        files_sha256={}, synthetic=True, qualified=False, qualification_artifact=None,
    )
    ds = PitDataset(
        provenance=placeholder,
        close=wide["close"], open=wide["open"], volume=wide["volume"],
        market_cap=wide["market_cap"], open_reliable=wide["open_reliable"],
        security_master=security_master, delistings=delistings, market=market,
    )
    return ds.with_provenance(Provenance(
        vendor="synthetic-golden", release="1", obtained_at=_SYNTHETIC_OBTAINED_AT,
        files_sha256={"canonical": canonical_sha256(ds)}, synthetic=True,
        qualified=False, qualification_artifact=None,
    ))
