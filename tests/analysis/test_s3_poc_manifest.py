"""Contratto del manifest congelato del POC S3 (#84).

Il manifest e' l'atto di pre-registrazione macchina-leggibile: i valori qui
asseriti sono quelli congelati dalla issue #84 prima del run definitivo. Un
cambiamento di uno di questi numeri e' una discontinuita' e va registrata nella
preregistrazione, non passata silenziosamente.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields as dc_fields
from datetime import date
from pathlib import Path

import pytest
import yaml

from src.analysis.s3_poc.manifest import ManifestError, load_manifest
from src.backtest.gates.runner import GateConfig
from tests.analysis.s3_poc_util import PRODUCTION_MANIFEST, load_raw_manifest, write_manifest_override


def load_raw() -> dict:
    return load_raw_manifest()


def write_override(tmp_path: Path, overrides: dict) -> Path:
    return write_manifest_override(tmp_path, overrides)


class TestManifestCongelato:
    def test_carica_e_hash(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        expected = hashlib.sha256(PRODUCTION_MANIFEST.read_bytes()).hexdigest()
        assert m.sha256 == expected
        assert m.poc_id == "s3-design-alignment-84"
        assert m.schema_version == "1"

    def test_split_sigillati(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.splits.dev_sample_end == date(2022, 12, 31)
        assert m.splits.holdout_start == date(2023, 1, 1)
        assert m.splits.holdout_end == date(2025, 12, 31)
        # il 2026 parziale resta fuori dalla metrica primaria
        assert m.splits.data_excluded_after == date(2025, 12, 31)

    def test_universo_pit(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.universe.min_history_sessions == 252
        assert m.universe.min_price_usd == 5.0
        assert m.universe.min_market_cap_usd == 2_000_000_000.0
        assert m.universe.min_adv_usd == 10_000_000.0
        assert m.universe.adv_window_sessions == 60
        assert m.universe.min_breadth == 200
        assert "OTC" not in m.universe.us_primary_exchanges
        assert m.universe.allowed_share_types == ["common"]

    def test_segnale_12_1(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.signal.lookback_sessions == 252
        assert m.signal.skip_sessions == 21
        assert m.signal.beta_window_sessions == 252
        assert m.signal.use_log_returns is True

    def test_costruzione_portafoglio(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.portfolio.n_deciles == 10
        assert m.portfolio.long_decile == 10
        assert m.portfolio.vol_window_sessions == 60
        assert m.portfolio.max_weight == 0.10
        assert m.portfolio.rebalance_frequency == "monthly"
        assert m.portfolio.execution == "next_session_open"

    def test_costi_e_stress_2x(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.costs.spread_bps == 20.0
        assert m.costs.impact_k == 10.0
        assert m.costs.stress_multiplier == 2.0

    def test_regole_di_selezione_e_combinato(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.selection_rules.sharpe_margin == 0.10
        assert m.selection_rules.risk_improvement_min == 0.15
        assert m.selection_rules.sharpe_tolerance == 0.05
        assert m.selection_rules.bootstrap_min_prob == 0.80
        assert m.combined_rules.primary_allocation == 0.10
        assert m.combined_rules.diagnostic_allocations == [0.05, 0.15]
        assert m.combined_rules.sharpe_gain_min == 0.05
        assert m.combined_rules.dd_es_worsening_max == 0.05
        assert m.combined_rules.dd_es_improvement_min == 0.10
        assert m.combined_rules.sharpe_reduction_max == 0.03

    def test_trial_registry_coerente_con_dsr(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.gates.n_trials == m.trial_registry.n_trials_for_dsr
        assert m.trial_registry.n_trials_for_dsr == len(m.trial_registry.entries)
        ids = [e["id"] for e in m.trial_registry.entries]
        assert "poc-84-A" in ids and "poc-84-B" in ids

    def test_gate_snapshot_senza_rilassamenti(self) -> None:
        """I gate del manifest devono coincidere con i GateConfig correnti.

        La issue vieta rilassamenti S3-specifici: se i default condivisi
        cambiano, il manifest va aggiornato consapevolmente (discontinuita').
        """
        m = load_manifest(PRODUCTION_MANIFEST)
        defaults = GateConfig()
        gate_fields = {f.name: getattr(defaults, f.name) for f in dc_fields(GateConfig)}
        for name, default_value in gate_fields.items():
            if name == "n_trials":
                # non e' una soglia: e' il conteggio onesto dei trial (registry),
                # il default 1 e' proprio l'inganno che il DSR corregge
                continue
            assert getattr(m.gates, name) == default_value, f"gate {name} diverge dal default"

    def test_regimi_almeno_tre(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert len(m.regimes.definitions) >= 3
        assert m.gates.min_passing_regimes == 3


class TestValidazioneManifest:
    def test_sezione_mancante(self, tmp_path: Path) -> None:
        raw = load_raw()
        del raw["universe"]
        p = tmp_path / "m.yaml"
        p.write_text(yaml.safe_dump(raw))
        with pytest.raises(ManifestError, match="universe"):
            load_manifest(p)

    def test_chiave_sconosciuta_rifiutata(self, tmp_path: Path) -> None:
        p = write_override(tmp_path, {"universo_extra": 1})
        with pytest.raises(ManifestError, match="universo_extra"):
            load_manifest(p)

    def test_chiave_sconosciuta_nella_sezione(self, tmp_path: Path) -> None:
        p = write_override(tmp_path, {"universe": {"min_breadth_extra": 5}})
        with pytest.raises(ManifestError, match="min_breadth_extra"):
            load_manifest(p)

    def test_tipo_errato(self, tmp_path: Path) -> None:
        p = write_override(tmp_path, {"universe": {"min_breadth": "tanti"}})
        with pytest.raises(ManifestError, match="min_breadth"):
            load_manifest(p)

    def test_override_valido_passa(self, tmp_path: Path) -> None:
        """I test usano manifest fixture derivati da quello di produzione."""
        p = write_override(tmp_path, {"universe": {"min_breadth": 5}})
        m = load_manifest(p)
        assert m.universe.min_breadth == 5

    def test_holdout_senza_signoff_dichiarato(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.holdout.signoff_required is True
        assert m.holdout.signoff_path == "docs/evidence/S3_POC_HOLDOUT_SIGNOFF_84.md"
        assert m.dataset.qualification_required is True


class TestSerializzabilita:
    def test_dump_json_dell_anatomia(self) -> None:
        """L'arteatto deve poter citare il manifest per intero."""
        m = load_manifest(PRODUCTION_MANIFEST)
        anatomy = m.to_dict()
        assert json.loads(json.dumps(anatomy))["splits"]["dev_sample_end"] == "2022-12-31"


class TestRobustnessGrid:
    """La griglia di robustezza e' fissata a priori nel manifest (non-trial
    dichiarato): il gate 3 la consuma senza cercarla sui risultati."""

    def test_griglia_congelata(self) -> None:
        m = load_manifest(PRODUCTION_MANIFEST)
        assert m.robustness.skip_sessions_grid == (15, 21, 30)
        assert m.robustness.vol_window_grid == (40, 60, 80)

    def test_griglia_non_tupla_di_interi_rifiutata(self, tmp_path: Path) -> None:
        p = write_override(tmp_path, {"robustness": {"skip_sessions_grid": [15, "tanti"]}})
        with pytest.raises(ManifestError, match="skip_sessions_grid"):
            load_manifest(p)


class TestOverridePerGriglia:
    """manifest_with_overrides: derivato tipizzato per i run diagnostici,
    sempre validato dallo stesso schema del manifest congelato."""

    def test_override_nested(self) -> None:
        from src.analysis.s3_poc.manifest import manifest_with_overrides

        m = load_manifest(PRODUCTION_MANIFEST)
        perturbato = manifest_with_overrides(m, {"signal": {"skip_sessions": 15}})
        assert perturbato.signal.skip_sessions == 15
        assert perturbato.signal.lookback_sessions == m.signal.lookback_sessions
        assert perturbato.universe == m.universe

    def test_override_chiave_sconosciuta_rifiutata(self) -> None:
        from src.analysis.s3_poc.manifest import manifest_with_overrides

        m = load_manifest(PRODUCTION_MANIFEST)
        with pytest.raises(ManifestError, match="skip_sessions_extra"):
            manifest_with_overrides(m, {"signal": {"skip_sessions_extra": 1}})

    def test_lo_sha256_resta_quello_del_file_congelato(self) -> None:
        """L'identita' del manifest derivato e' il file congelato di partenza:
        l'override e' una perturbazione dichiarata, non una nuova taratura."""
        from src.analysis.s3_poc.manifest import manifest_with_overrides

        m = load_manifest(PRODUCTION_MANIFEST)
        perturbato = manifest_with_overrides(m, {"portfolio": {"vol_window_sessions": 40}})
        assert perturbato.sha256 == m.sha256
