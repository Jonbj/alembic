"""Eligibilita' PIT al ribilancio del POC S3 (#84).

La membership si valuta punto-nel-tempo a ogni ribilancio: i superstiti
futuri non contaminano le selezioni storiche, e un security inidoneo si
esclude localmente senza cancellare la data.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.analysis.s3_poc.eligibility import eligible_at
from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.s3_poc_util import write_manifest_override

# Default del builder: prezzo 50..61, volume 1M azioni, cap ~2.5-3mlr: eleggibili.


def make_spec(**kwargs) -> SyntheticSpec:
    defaults = dict(
        start=date(2019, 1, 1),
        end=date(2021, 12, 31),
        securities=tuple(
            SecuritySpec(security_id=f"S{i:03d}", start_price=50.0 + i)
            for i in range(10)
        ),
    )
    defaults.update(kwargs)
    return SyntheticSpec(**defaults)


@pytest.fixture(scope="module")
def manifest_small_breadth(tmp_path_factory) -> load_manifest:
    p = write_manifest_override(
        tmp_path_factory.mktemp("manifest"), {"universe": {"min_breadth": 3}}
    )
    return load_manifest(p)


class TestFiltriPIT:
    def test_eleggibili_di_default(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec())
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        # 252 sedute di storia dal 2019-01-01: tutte dentro dal 2020-01
        assert set(res.eligible) == {f"S{i:03d}" for i in range(10)}
        assert res.sufficient is True

    def test_storia_insufficiente_esclude_localmente(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="IPO2021", start=date(2021, 6, 1)),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert "IPO2021" not in res.eligible
        assert set(res.eligible) == {f"S{i:03d}" for i in range(5)}
        assert res.excluded_counts.get("history") == 1

    def test_prezzo_sotto_soglia(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="CHEAP", start_price=4.0),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert "CHEAP" not in res.eligible
        assert res.excluded_counts.get("price") == 1

    def test_cap_sotto_soglia(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="SMALLCAP", shares_outstanding=10_000_000.0),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert "SMALLCAP" not in res.eligible
        assert res.excluded_counts.get("market_cap") == 1

    def test_adv_sotto_soglia(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="ILLIQ", volume_shares=100_000.0),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert "ILLIQ" not in res.eligible
        assert res.excluded_counts.get("adv") == 1

    def test_non_common_escluso(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="ETF", share_type="etf"),
            SecuritySpec(security_id="ADR", share_type="adr"),
            SecuritySpec(security_id="PREF", share_type="preferred"),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert not {"ETF", "ADR", "PREF"} & set(res.eligible)
        assert res.excluded_counts.get("security_type") == 3

    def test_otc_escluso(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="OTC1", primary_exchange="OTC"),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert "OTC1" not in res.eligible

    def test_delistato_non_eleggibile(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="GONE", delisting_date=date(2021, 3, 15), delisting_return=-1.0),
            *make_spec().securities[:5],
        )))
        prima = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-03-12"))
        dopo = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-03-16"))
        assert "GONE" in prima.eligible
        assert "GONE" not in dopo.eligible


class TestNessunLeakage:
    def test_troncare_il_futuro_non_cambia_il_passato(self, manifest_small_breadth) -> None:
        """Il golden test: l'eligibilita' a t non vede nulla di posteriore a t."""
        ds = build_synthetic_dataset(make_spec(securities=(
            # cap sotto i 2mlr solo nella seconda meta' del 2021: a t e' ancora dentro
            # (vol 0: cammino deterministico, niente sensibilita' al seed)
            SecuritySpec(security_id="CHEAPLATER", start_price=90.0, daily_vol=0.0, drift=-0.30),
            SecuritySpec(security_id="GONE", delisting_date=date(2021, 9, 30), delisting_return=-1.0),
            *make_spec().securities[:5],
        )))
        t = pd.Timestamp("2021-06-30")
        pieno = eligible_at(ds, manifest_small_breadth, t)
        # dataset troncato: tutte le righe dopo t rimosse (nessun futuro disponibile)
        troncato = ds.truncate_at(t)
        tagliato = eligible_at(troncato, manifest_small_breadth, t)
        assert set(pieno.eligible) == set(tagliato.eligible)
        # CHEAPLATER sara' diventato economico solo dopo t: a t resta eleggibile
        assert "CHEAPLATER" in pieno.eligible

    def test_membership_futura_non_contamina(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=(
            SecuritySpec(security_id="LATER", start=date(2021, 10, 1)),
            *make_spec().securities[:5],
        )))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert "LATER" not in res.eligible


class TestBreadth:
    def test_sotto_min_breadth_marca_insufficiente(self, tmp_path) -> None:
        p = write_manifest_override(tmp_path, {"universe": {"min_breadth": 100}})
        m = load_manifest(p)
        ds = build_synthetic_dataset(make_spec())
        res = eligible_at(ds, m, pd.Timestamp("2021-06-30"))
        assert len(res.eligible) == 10
        assert res.sufficient is False

    def test_esattamente_min_breadth_e_sufficiente(self, manifest_small_breadth) -> None:
        ds = build_synthetic_dataset(make_spec(securities=make_spec().securities[:3]))
        res = eligible_at(ds, manifest_small_breadth, pd.Timestamp("2021-06-30"))
        assert len(res.eligible) == 3
        assert res.sufficient is True
