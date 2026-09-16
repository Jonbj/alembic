"""Costruzione del portafoglio S3 del POC (#84).

Top decile long-only, sizing inverse-vol su 60 sedute, pesi normalizzati
alla manica, cap 10% per security con ridistribuzione iterativa fra i non
cappati. Cassa residua solo quando l'allocazione piena e' matematicamente
impossibile.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.analysis.s3_poc.construction import (
    apply_iterative_cap,
    inverse_vol_weights,
    select_top_decile,
)
from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.s3_poc_util import write_manifest_override


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    return load_manifest(write_manifest_override(tmp_path_factory.mktemp("m"), {}))


class TestTopDecile:
    def test_seleziona_il_decimo_decile(self) -> None:
        signals = {f"S{i:02d}": float(i) for i in range(20)}
        assert select_top_decile(signals, n_deciles=10, long_decile=10) == ["S18", "S19"]

    def test_con_25_ne_prende_3(self) -> None:
        signals = {f"S{i:02d}": float(i) for i in range(25)}
        # decile = ceil(rank*10/25): rank 23,24,25 -> ceil(9.2),ceil(9.6),ceil(10)
        assert select_top_decile(signals, n_deciles=10, long_decile=10) == [
            "S22", "S23", "S24",
        ]

    def test_meno_di_10_prende_l_ultimo_decile_vuoto_o_quasi(self) -> None:
        signals = {f"S{i:02d}": float(i) for i in range(9)}
        # ceil(rank*10/9): rank 8 -> ceil(8.9)=9, rank 9 -> 10: solo l'ultimo e' decile 10
        assert select_top_decile(signals, n_deciles=10, long_decile=10) == ["S08"]

    def test_vuoto_con_meno_di_10_se_la_formula_non_lo_permette(self) -> None:
        signals = {f"S{i:02d}": float(i) for i in range(4)}
        # ceil(4*10/4)=10: S03 e' decile 10 anche qui
        assert select_top_decile(signals, n_deciles=10, long_decile=10) == ["S03"]


class TestCapIterativo:
    def test_un_solo_cap_e_ridistribuzione(self) -> None:
        weights = {"A": 0.55, **{f"S{i}": 0.05 for i in range(9)}}
        capped = apply_iterative_cap(weights, cap=0.10)
        assert capped["A"] == pytest.approx(0.10)
        assert sum(capped.values()) == pytest.approx(1.0)
        assert all(w <= 0.10 + 1e-12 for w in capped.values())

    def test_due_cap_che_ne_generano_un_terzo(self) -> None:
        # tre security sopra il cap: la ridistribuzione porta gli altri
        # esattamente al cap senza superarlo
        weights = {"A": 0.30, "B": 0.20, "C": 0.12,
                   **{f"S{i}": 0.38 / 7 for i in range(7)}}
        capped = apply_iterative_cap(weights, cap=0.10)
        assert all(w <= 0.10 + 1e-12 for w in capped.values())
        assert sum(capped.values()) == pytest.approx(1.0)

    def test_impossibile_lascia_cassa(self) -> None:
        weights = {"A": 0.7, "B": 0.2, "C": 0.1}
        capped = apply_iterative_cap(weights, cap=0.10)
        assert all(w <= 0.10 + 1e-12 for w in capped.values())
        assert sum(capped.values()) == pytest.approx(0.30)  # 3 x 10%, resto cassa

    def test_gia_sotto_cap_invariato(self) -> None:
        weights = {f"S{i}": 0.1 for i in range(10)}
        assert apply_iterative_cap(weights, cap=0.10) == weights


class TestInverseVol:
    def test_volguali_pesi_uguali(self, manifest) -> None:
        ds = build_synthetic_dataset(SyntheticSpec(
            start=date(2019, 1, 1), end=date(2021, 12, 31),
            securities=tuple(
                SecuritySpec(security_id=f"S{i:02d}", daily_vol=0.02)
                for i in range(10)
            ),
        ))
        w = inverse_vol_weights(ds, manifest, pd.Timestamp("2021-06-30"),
                                tuple(f"S{i:02d}" for i in range(10)))
        assert len(w) == 10
        # stesso vol parametrico: cluster stretto, somma 1, rispetto del cap
        assert sum(w.values()) == pytest.approx(1.0)
        assert all(w <= 0.10 + 1e-9 for w in w.values())
        assert max(w.values()) >= 0.09

    def test_bassa_vol_pesa_piu(self, manifest) -> None:
        ds = build_synthetic_dataset(SyntheticSpec(
            start=date(2019, 1, 1), end=date(2021, 12, 31),
            securities=(
                SecuritySpec(security_id="CALMA", daily_vol=0.01),
                *[SecuritySpec(security_id=f"T{i:02d}", daily_vol=0.02) for i in range(19)],
            ),
        ))
        secs = ("CALMA",) + tuple(f"T{i:02d}" for i in range(19))
        w = inverse_vol_weights(ds, manifest, pd.Timestamp("2021-06-30"), secs)
        altri = [w[s] for s in secs if s != "CALMA"]
        assert w["CALMA"] > 1.5 * max(altri)

    def test_finestra_60_sedute(self, manifest) -> None:
        """La vol e' quella trailing di 60 sedute: un passato piu' remoto
        con vol diversa non conta."""
        ds = build_synthetic_dataset(SyntheticSpec(
            start=date(2019, 1, 1), end=date(2021, 12, 31),
            securities=tuple(
                SecuritySpec(security_id=f"S{i:02d}", daily_vol=0.01)
                for i in range(10)
            ),
        ))
        # vol alta solo nel passato remoto di S00 (fuori dalla finestra 60)
        close = ds.close.copy()
        idx = ds.close.index.get_indexer([pd.Timestamp("2021-06-30")])[0]
        vecchie = close.index[idx - 200 : idx - 60]
        close.loc[vecchie, "S00"] *= [1.0 + 0.05 * ((-1) ** k) for k in range(len(vecchie))]
        from src.analysis.s3_poc.dataset import PitDataset
        ds2 = PitDataset(
            provenance=ds.provenance, close=close, open=ds.open, volume=ds.volume,
            market_cap=ds.market_cap, open_reliable=ds.open_reliable,
            security_master=ds.security_master, delistings=ds.delistings, market=ds.market,
        )
        secs = tuple(f"S{i:02d}" for i in range(10))
        w = inverse_vol_weights(ds2, manifest, pd.Timestamp("2021-06-30"), secs)
        altri = [w[s] for s in secs if s != "S00"]
        assert w["S00"] == pytest.approx(sum(altri) / len(altri), rel=0.05)

    def test_cap_10_applicato_dal_costruttore(self, manifest) -> None:
        ds = build_synthetic_dataset(SyntheticSpec(
            start=date(2019, 1, 1), end=date(2021, 12, 31),
            securities=(
                SecuritySpec(security_id="MOLTOCALMA", daily_vol=0.002),
                *[SecuritySpec(security_id=f"S{i:02d}", daily_vol=0.03) for i in range(11)],
            ),
        ))
        secs = ("MOLTOCALMA",) + tuple(f"S{i:02d}" for i in range(11))
        w = inverse_vol_weights(ds, manifest, pd.Timestamp("2021-06-30"), secs)
        assert all(v <= 0.10 + 1e-9 for v in w.values())
        assert sum(w.values()) == pytest.approx(1.0)
