"""Valutazione standalone delle varianti A/B del POC S3 (#84).

Gate correnti senza rilassamenti (GateConfig dal manifest), regimi 4 fette
sovrapposte, stress storici di produzione + momentum crash dal manifest,
DSR con il numero vero di trial del registry, attribuzione (beta vs
mercato, concentrazione settore, turnover, esposizione lorda, cash drag).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.test_s3_poc_engine import hand_dataset
from tests.analysis.s3_poc_util import write_manifest_override


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    """Manifest di prova: breadth basso e walk-forward corto per stare nei
    test (le soglie dei gate restano quelle di produzione)."""
    return load_manifest(write_manifest_override(tmp_path_factory.mktemp("m"), {
        "universe": {"min_breadth": 3},
        "walkforward": {"in_sample_months": 12, "oos_months": 6, "step_months": 6},
    }))


def drift_dataset(start=date(2019, 1, 1), end=date(2021, 12, 31)):
    specs = tuple(
        SecuritySpec(security_id=f"S{i:02d}", daily_vol=0.01, drift=-0.20 + 0.05 * i,
                     sector=["TECH", "FIN", "ENER"][i % 3])
        for i in range(10)
    ) + (
        SecuritySpec(security_id="TOP", daily_vol=0.01, drift=0.35, sector="TECH"),
        SecuritySpec(security_id="BADTOP", daily_vol=0.01, drift=0.30, sector="FIN"),
    )
    return build_synthetic_dataset(SyntheticSpec(start=start, end=end, securities=specs))


class TestGateConfigDalManifest:
    def test_snapshot_senza_rilassamenti(self, manifest) -> None:
        from src.analysis.s3_poc.evaluation import gate_config_from_manifest
        from src.backtest.gates.runner import GateConfig

        cfg = gate_config_from_manifest(manifest)
        assert isinstance(cfg, GateConfig)
        g = manifest.gates
        assert cfg.n_trials == g.n_trials == manifest.trial_registry.n_trials_for_dsr
        assert cfg.min_sharpe == g.min_sharpe
        assert cfg.min_oos_sharpe == g.min_oos_sharpe
        assert cfg.min_passing_regimes == g.min_passing_regimes
        assert cfg.max_drawdown_allowed == g.max_drawdown_allowed
        assert cfg.min_dsr == g.min_dsr
        assert cfg.max_cv == g.max_cv
        assert cfg.min_cumulative_return == g.min_cumulative_return


class TestRegimi:
    def test_quattro_fette_sma200_e_vol60(self, manifest) -> None:
        """Mercato in trend rialzista poi ribassista: bull e bear non vuoti;
        le fette vol coprono tutto il periodo di valutazione."""
        from src.analysis.s3_poc.evaluation import regime_slices

        ds = hand_dataset()
        # mercato craftato: sale fino a meta' 2020 poi scende
        sessions = ds.sessions
        n = len(sessions)
        up = np.linspace(400.0, 600.0, n // 2)
        down = np.linspace(600.0, 300.0, n - n // 2)
        market = pd.Series(np.concatenate([up, down]), index=sessions)
        from src.analysis.s3_poc.dataset import PitDataset
        ds = PitDataset(
            provenance=ds.provenance, close=ds.close, open=ds.open, volume=ds.volume,
            market_cap=ds.market_cap, open_reliable=ds.open_reliable,
            security_master=ds.security_master, delistings=ds.delistings, market=market,
        )
        rets = pd.Series(0.001, index=sessions[(sessions >= pd.Timestamp("2020-01-01"))])
        reg = regime_slices(ds, manifest, rets)
        assert set(reg) == {"bull", "bear", "high_vol", "low_vol"}
        assert len(reg["bear"]) > 0
        assert len(reg["bull"]) > 0
        # ogni seduta di valutazione con SMA definita cade in una sola fetta trend
        for nome in ("bull", "bear"):
            assert reg[nome].index.is_unique
        # le fette vol si spartiscono la serie (mediana come split)
        assert len(reg["high_vol"]) + len(reg["low_vol"]) >= len(rets) - 1


class TestStress:
    def test_stress_storici_e_crash_del_manifest(self, manifest) -> None:
        from src.analysis.s3_poc.evaluation import stress_slices

        ds = hand_dataset()
        sessions = ds.sessions
        rets = pd.Series(0.0005, index=sessions)
        stress = stress_slices(rets, manifest)
        # 2020_covid e 2022_rates arrivano dalla tabella di produzione
        assert "2020_covid" in stress
        # 2020_rebound arriva dal manifest (momentum crash), 2009 no (fuori sample)
        assert "2020_rebound" in stress
        assert "2009_rebound" not in stress
        for name, sl in stress.items():
            assert len(sl) > 0


class TestValutazione:
    def test_end_to_end_su_sintetico(self, manifest) -> None:
        from src.analysis.s3_poc.evaluation import evaluate_variant

        ds = drift_dataset()
        ev = evaluate_variant(ds, manifest, variant="B",
                              period_start=pd.Timestamp("2020-01-01"),
                              period_end=pd.Timestamp("2021-06-30"))
        # metriche standalone di produzione
        for k in ("sharpe", "max_drawdown", "expected_shortfall", "annualized_return",
                  "annualized_vol", "n_sessions"):
            assert k in ev.metrics
        assert np.isfinite(ev.metrics["sharpe"])
        # gate correnti, tutti e cinque presenti
        assert set(ev.gates.gate_results) == {
            "gate_1_significance", "gate_2_walkforward", "gate_3_robustness",
            "gate_4_regime", "gate_5_stress",
        }
        # DSR con il numero vero di trial
        assert ev.dsr["n_trials"] == manifest.trial_registry.n_trials_for_dsr
        assert "dsr" in ev.dsr and 0.0 <= ev.dsr["dsr"] <= 1.0
        # walk-forward: finestre OOS dentro il periodo
        assert ev.windows
        assert all(w["sharpe"] == w["sharpe"] for w in ev.windows)  # finite (no NaN)
        # attribuzione
        assert np.isfinite(ev.attribution["beta_vs_market"])
        assert ev.attribution["annualized_turnover"] > 0
        assert 0.0 <= ev.attribution["avg_gross_exposure"] <= 1.0
        assert 0.0 <= ev.attribution["avg_cash_weight"] <= 1.0
        assert 0.0 < ev.attribution["sector_hhi_avg"] <= 1.0
        # i costi totali alimentano la regola di deterioramento della selezione
        assert ev.attribution["total_cost_usd"] > 0
        assert ev.attribution["annualized_cost_bps"] > 0
        assert ev.attribution["average_cost_per_rebalance_bps"] > 0
        # la serie dei rendimenti resta disponibile per il paired bootstrap A/B
        assert len(ev.returns) == ev.coverage["n_sessions"]
        # coverage e grado decisionale
        assert ev.coverage["n_sessions"] > 0
        assert ev.decision_grade is True
        assert ev.variant == "B"

    def test_robustness_grid_dal_manifest(self, manifest) -> None:
        """Il gate 3 consuma la griglia congelata: 9 run, il centro e' la
        taratura di produzione (identico al run pieno)."""
        from src.analysis.s3_poc.evaluation import evaluate_variant, robustness_sharpes

        ds = drift_dataset()
        kw = dict(period_start=pd.Timestamp("2020-01-01"), period_end=pd.Timestamp("2020-06-30"))
        sharpes = robustness_sharpes(ds, manifest, variant="B", **kw)
        expected = len(manifest.robustness.skip_sessions_grid) * len(manifest.robustness.vol_window_grid)
        assert len(sharpes) == expected
        ev = evaluate_variant(ds, manifest, variant="B", **kw)
        # il centro della griglia riproduce il run pieno
        assert max(abs(s - ev.metrics["sharpe"]) for s in sharpes) == pytest.approx(0.0, abs=1e-12)
        g3 = ev.gates.gate_results["gate_3_robustness"]
        assert np.isfinite(g3.details["cv"])

    def test_scenario_costo_2x_valutabile(self, manifest) -> None:
        from src.analysis.s3_poc.evaluation import evaluate_variant

        ds = drift_dataset()
        kw = dict(period_start=pd.Timestamp("2020-01-01"), period_end=pd.Timestamp("2020-09-30"))
        base = evaluate_variant(ds, manifest, variant="B", cost_multiplier=1.0, **kw)
        doppio = evaluate_variant(ds, manifest, variant="B",
                                  cost_multiplier=manifest.costs.stress_multiplier, **kw)
        assert base.cost_multiplier == 1.0
        assert doppio.cost_multiplier == 2.0
        # su sintetico i costi mangiano rendimento: NAV finale inferiore
        assert doppio.metrics["final_nav"] < base.metrics["final_nav"]

    def test_delisting_non_risolto_declassa_la_valutazione(self, manifest) -> None:
        from src.analysis.s3_poc.evaluation import evaluate_variant

        ds = hand_dataset(delistings=(("ZMISS", date(2020, 4, 15), -0.5, True),))
        ev = evaluate_variant(ds, manifest, variant="B",
                              period_start=pd.Timestamp("2020-01-01"),
                              period_end=pd.Timestamp("2020-09-30"))
        assert ev.decision_grade is False
        assert ev.unresolved_delistings

    def test_serializzabile_per_l_artefatto(self, manifest) -> None:
        import json

        from src.analysis.s3_poc.evaluation import evaluate_variant

        ds = drift_dataset()
        ev = evaluate_variant(ds, manifest, variant="A",
                              period_start=pd.Timestamp("2020-01-01"),
                              period_end=pd.Timestamp("2020-09-30"))
        dumped = json.dumps(ev.to_dict())
        assert json.loads(dumped)["variant"] == "A"
        assert "gates" in json.loads(dumped)
