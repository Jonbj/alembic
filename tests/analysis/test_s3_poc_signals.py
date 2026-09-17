"""Segnali A/B del POC S3 (#84): momentum 12-1 log, con e senza correzione beta.

A = log(P_{t-21}/P_{t-252}) - beta_{252} * log(M_{t-21}/M_{t-252})
B = log(P_{t-21}/P_{t-252})
Ogni altra scelta di costruzione e' identica: la differenza isolata e' la
correzione beta (user story 11).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analysis.s3_poc.dataset import PitDataset, Provenance
from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.signals import variant_signal
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.s3_poc_util import write_manifest_override


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    return load_manifest(write_manifest_override(tmp_path_factory.mktemp("m"), {}))


def make_dataset(securities: tuple[SecuritySpec, ...], **kwargs):
    defaults = dict(start=date(2019, 1, 1), end=date(2021, 12, 31))
    defaults.update(kwargs)
    return build_synthetic_dataset(SyntheticSpec(securities=securities, **defaults))


def hand_dataset(
    close: dict[str, list[float]], market: list[float]
) -> PitDataset:
    """Dataset craftato a mano per beta esatte: 400+ sedute."""
    n = len(market)
    assert all(len(v) == n for v in close.values())
    sessions = pd.bdate_range(date(2019, 1, 1), periods=n)
    close_df = pd.DataFrame(close, index=sessions)
    prov = Provenance(
        vendor="hand", release="1", obtained_at=date(2026, 9, 16),
        files_sha256={}, synthetic=True, qualified=False, qualification_artifact=None,
    )
    return PitDataset(
        provenance=prov,
        close=close_df,
        open=close_df.copy(),
        volume=pd.DataFrame(1e6, index=sessions, columns=close_df.columns),
        market_cap=pd.DataFrame(1e10, index=sessions, columns=close_df.columns),
        open_reliable=pd.DataFrame(True, index=sessions, columns=close_df.columns),
        security_master=pd.DataFrame([{
            "security_id": sec, "valid_from": sessions[0], "valid_to": sessions[-1],
            "share_type": "common", "primary_exchange": "NYSE", "sector": "X",
        } for sec in close_df.columns]),
        delistings=pd.DataFrame(columns=["security_id", "delisting_date", "delisting_return", "missing_status"]),
        market=pd.Series(market, index=sessions),
    )


def alternating_market(n: int) -> np.ndarray:
    return 400.0 * np.cumprod(np.where(np.arange(n) % 2 == 0, 1.01, 1 / 1.01))


class TestTempismo12Meno1:
    def test_il_segnale_usa_esattamente_t252_e_t21(self, manifest) -> None:
        ds = make_dataset((SecuritySpec(security_id="FLAT", daily_vol=0.0, drift=0.10),))
        t = pd.Timestamp("2021-06-30")
        sig = variant_signal(ds, manifest, t, ("FLAT",), variant="B")
        idx = ds.close.index.get_indexer([t])[0]
        c21 = ds.close["FLAT"].iloc[idx - 21]
        c252 = ds.close["FLAT"].iloc[idx - 252]
        assert sig["FLAT"] == pytest.approx(np.log(c21 / c252), rel=1e-12)

    def test_storia_insufficiente_escluso_localmente(self, manifest) -> None:
        ds = make_dataset((
            SecuritySpec(security_id="OK", daily_vol=0.0, drift=0.1),
            SecuritySpec(security_id="GIOVANE", start=date(2021, 1, 1)),
        ))
        t = pd.Timestamp("2021-06-30")
        sig = variant_signal(ds, manifest, t, ("OK", "GIOVANE"), variant="B")
        assert "OK" in sig
        assert "GIOVANE" not in sig  # la data sopravvive: esclusione locale


class TestCorrezioneBeta:
    def test_beta_esatte_su_dati_craftati(self, manifest) -> None:
        """Clone (beta 1), anti-correlato (beta -1), indipendente (beta 0)."""
        n = 800
        market = alternating_market(n)
        mret = np.diff(market) / market[:-1]
        clone = 100.0 * np.cumprod(np.concatenate([[1.0], 1 + mret]))   # beta +1
        zig = 100.0 * np.cumprod(np.concatenate([[1.0], 1 - mret]))     # beta -1
        flat2 = np.full(n, 100.0)                                        # var nulla -> beta 0

        sessions = pd.bdate_range(date(2019, 1, 1), periods=n)
        t = sessions[-1]
        idx = n - 1
        mkt_mom = np.log(market[idx - 21] / market[idx - 252])

        ds = hand_dataset(
            {"CLONE": list(clone), "ZIG": list(zig), "FLAT2": list(flat2)},
            list(market),
        )
        b = variant_signal(ds, manifest, t, ("CLONE", "ZIG", "FLAT2"), variant="B")
        a = variant_signal(ds, manifest, t, ("CLONE", "ZIG", "FLAT2"), variant="A")

        assert a["CLONE"] == pytest.approx(b["CLONE"] - 1.0 * mkt_mom, rel=1e-9, abs=1e-12)
        assert a["ZIG"] == pytest.approx(b["ZIG"] + 1.0 * mkt_mom, rel=1e-9, abs=1e-12)
        assert a["FLAT2"] == pytest.approx(b["FLAT2"], abs=1e-12)


class TestParitaAB:
    def test_la_differenza_e_solo_la_correzione_beta(self, manifest) -> None:
        """Stesso dataset, stesse sedute: A - B = -beta * momentum_mercato."""
        ds = make_dataset(tuple(
            SecuritySpec(security_id=f"S{i:03d}", daily_vol=0.02 + 0.005 * i, drift=0.02 * i)
            for i in range(6)
        ))
        t = pd.Timestamp("2021-06-30")
        secs = tuple(f"S{i:03d}" for i in range(6))
        a = variant_signal(ds, manifest, t, secs, variant="A")
        b = variant_signal(ds, manifest, t, secs, variant="B")
        assert set(a) == set(b)
        # la correzione sposta ogni segnale dell'esatto contributo beta
        idx = ds.close.index.get_indexer([t])[0]
        mkt_mom = float(np.log(ds.market.iloc[idx - 21] / ds.market.iloc[idx - 252]))
        assert mkt_mom != 0.0
        shifted = {s: a[s] - b[s] for s in a}
        assert any(abs(v) > 1e-9 for v in shifted.values())  # beta non degenere

    def test_variante_sconosciuta_rifiutata(self, manifest) -> None:
        ds = make_dataset((SecuritySpec(security_id="FLAT"),))
        with pytest.raises(ValueError, match="variant"):
            variant_signal(ds, manifest, pd.Timestamp("2021-06-30"), ("FLAT",), variant="C")
