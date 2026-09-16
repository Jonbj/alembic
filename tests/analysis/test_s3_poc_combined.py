"""Test combinato S1 invariato + punti di cassa sostituiti da S3 (#84).

r_comb = r_S1 + w x (r_S3_net - cash_return), w = 0.10 primario (5% e 15%
solo diagnostici). Delta contro S1 standalone su Sharpe/MaxDD/ES e
bootstrap iid (10000 estrazioni, seed congelato) sulla differenza. Senza
serie S1 niente valutazione: fail-closed.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.s3_poc_util import write_manifest_override


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    return load_manifest(write_manifest_override(tmp_path_factory.mktemp("m"), {
        "universe": {"min_breadth": 3},
    }))


def s3_returns(manifest, start=date(2019, 1, 1), end=date(2020, 12, 31)) -> pd.Series:
    """Manica S3 deterministica: 12 security, drift crescente."""
    from src.analysis.s3_poc.engine import run_sleeve

    specs = tuple(
        SecuritySpec(security_id=f"S{i:02d}", daily_vol=0.01, drift=-0.20 + 0.05 * i)
        for i in range(10)
    ) + (
        SecuritySpec(security_id="TOP", daily_vol=0.01, drift=0.35),
        SecuritySpec(security_id="BADTOP", daily_vol=0.01, drift=0.30),
    )
    ds = build_synthetic_dataset(SyntheticSpec(start=start, end=end, securities=specs))
    res = run_sleeve(ds, manifest, variant="B",
                     start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-12-31"))
    return res.returns


def serie(costante: float, index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(costante, index=index)


class TestCombinazione:
    def test_formula_s1_piu_w_per_s3(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined
        from src.backtest.metrics.performance import sharpe_ratio

        r3 = s3_returns(manifest)
        r1 = serie(0.0002, r3.index) + pd.Series(
            np.random.default_rng(1).normal(0, 0.001, len(r3)), index=r3.index
        )
        rep = evaluate_combined(r1, r3, manifest)
        assert rep.evaluability is True
        w = manifest.combined_rules.primary_allocation
        atteso = r1 + w * (r3 - manifest.combined_rules.cash_return)
        cfg = rep.allocations[0]
        assert cfg["allocation"] == w
        assert cfg["sharpe"] == pytest.approx(sharpe_ratio(atteso, periods=252), rel=1e-9)

    def test_allocazioni_dal_manifest_primaria_e_diagnostiche(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        r3 = s3_returns(manifest)
        r1 = serie(0.0001, r3.index)
        rep = evaluate_combined(r1, r3, manifest)
        allocs = [a["allocation"] for a in rep.allocations]
        assert manifest.combined_rules.primary_allocation in allocs
        for d in manifest.combined_rules.diagnostic_allocations:
            assert d in allocs
        assert rep.primary_allocation == manifest.combined_rules.primary_allocation

    def test_cash_return_non_zero_sposta_la_formula(self, tmp_path_factory, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined
        from src.backtest.metrics.performance import sharpe_ratio

        m = load_manifest(write_manifest_override(tmp_path_factory.mktemp("cr"), {
            "universe": {"min_breadth": 3},
            "combined_rules": {"cash_return": 0.02},
        }))
        r3 = s3_returns(manifest)
        r1 = serie(0.0, r3.index)
        rep = evaluate_combined(r1, r3, m)
        w = m.combined_rules.primary_allocation
        atteso = r1 + w * (r3 - 0.02 / 252.0)  # giornalizzata
        assert rep.allocations[0]["sharpe"] == pytest.approx(
            sharpe_ratio(atteso, periods=252), rel=1e-9
        )

    def test_allineamento_sull_intersezione(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        r3 = s3_returns(manifest)
        # S1 esiste solo su una sotto-serie di date
        r1 = serie(0.0001, r3.index[10:])
        rep = evaluate_combined(r1, r3, manifest)
        assert rep.overlap["n_obs"] == len(r3) - 10


class TestDeltaEBootstrap:
    def test_delta_contro_s1_standalone(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined
        from src.backtest.metrics.performance import sharpe_ratio
        from src.backtest.metrics.risk import max_drawdown, expected_shortfall

        r3 = s3_returns(manifest)
        rng = np.random.default_rng(7)
        r1 = serie(0.0002, r3.index) + pd.Series(rng.normal(0, 0.002, len(r3)), index=r3.index)
        rep = evaluate_combined(r1, r3, manifest)
        cfg = rep.allocations[0]
        assert cfg["sharpe_delta"] == pytest.approx(
            cfg["sharpe"] - sharpe_ratio(r1, periods=252), rel=1e-9
        )
        assert cfg["max_drawdown"] == pytest.approx(max_drawdown(
            r1 + manifest.combined_rules.primary_allocation * r3
        ), rel=1e-9)
        assert cfg["expected_shortfall"] == pytest.approx(expected_shortfall(
            r1 + manifest.combined_rules.primary_allocation * r3
        ), rel=1e-9)

    def test_bootstrap_deterministico_e_limitato(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        r3 = s3_returns(manifest)
        rng = np.random.default_rng(3)
        r1 = pd.Series(rng.normal(0.0003, 0.002, len(r3)), index=r3.index)
        rep1 = evaluate_combined(r1, r3, manifest)
        rep2 = evaluate_combined(r1, r3, manifest)
        for a, b in zip(rep1.allocations, rep2.allocations):
            assert a["bootstrap_prob"] == b["bootstrap_prob"]
            assert 0.0 <= a["bootstrap_prob"] <= 1.0

    def test_bootstrap_estremi(self, manifest) -> None:
        """S3 nettamente migliore: probabilita' 1; nettamente peggiore: 0.
        (rumore minimo su entrambe le serie: Sharpe definito, esito certo)"""
        from src.analysis.s3_poc.combined import evaluate_combined

        idx = pd.bdate_range(date(2020, 1, 1), date(2020, 12, 31))
        rng = np.random.default_rng(5)
        r1 = pd.Series(rng.normal(0.0, 0.0005, len(idx)), index=idx)
        buona = pd.Series(rng.normal(0.002, 0.0005, len(idx)), index=idx)
        cattiva = pd.Series(rng.normal(-0.002, 0.0005, len(idx)), index=idx)
        assert evaluate_combined(r1, buona, manifest).allocations[0]["bootstrap_prob"] == pytest.approx(1.0)
        assert evaluate_combined(r1, cattiva, manifest).allocations[0]["bootstrap_prob"] == pytest.approx(0.0)

    def test_numero_di_estrazioni_e_seed_dal_manifest(self, tmp_path_factory, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        m = load_manifest(write_manifest_override(tmp_path_factory.mktemp("bs"), {
            "universe": {"min_breadth": 3},
            "combined_rules": {"bootstrap_draws": 500, "bootstrap_seed": 11},
        }))
        r3 = s3_returns(manifest)
        r1 = serie(0.0001, r3.index)
        rep = evaluate_combined(r1, r3, m)
        assert rep.bootstrap_draws == 500
        # seed diverso da quello di produzione: esito può divergere ma resta in [0,1]
        assert 0.0 <= rep.allocations[0]["bootstrap_prob"] <= 1.0


class TestFailClosed:
    def test_senza_s1_non_valutabile(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        r3 = s3_returns(manifest)
        rep = evaluate_combined(None, r3, manifest)
        assert rep.evaluability is False
        assert rep.allocations == []

    def test_senza_intersezione_non_valutabile(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        r3 = s3_returns(manifest)
        idx_senza = pd.bdate_range(date(2016, 1, 1), date(2016, 12, 31))
        r1 = serie(0.0001, idx_senza)
        rep = evaluate_combined(r1, r3, manifest)
        assert rep.evaluability is False

    def test_serializzabile(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        r3 = s3_returns(manifest)
        r1 = serie(0.0001, r3.index)
        rep = evaluate_combined(r1, r3, manifest)
        d = json.loads(json.dumps(rep.to_dict()))
        assert d["evaluability"] is True
        assert d["primary_allocation"] == manifest.combined_rules.primary_allocation
