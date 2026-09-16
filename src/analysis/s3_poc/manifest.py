"""Manifest congelato del POC S3: pre-registrazione macchina-leggibile.

Tutte le soglie, le finestre, i costi e le regole di esito del POC vivono in un
unico YAML firmato dal proprio sha256. Il runner rifiuta configurazioni che
divergono dallo schema (chiavi sconosciute = tentativo di taratura silenziosa).
Modificare un valore qui dentro dopo il run definitivo e' una discontinuita':
va registrata nella preregistrazione, non passata sotto silenzio.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


class ManifestError(ValueError):
    """Il manifest viola lo schema congelato."""


@dataclass(frozen=True)
class SplitsCfg:
    dev_sample_end: date
    holdout_start: date
    holdout_end: date
    data_excluded_after: date


@dataclass(frozen=True)
class UniverseCfg:
    min_history_sessions: int
    min_price_usd: float
    min_market_cap_usd: float
    min_adv_usd: float
    adv_window_sessions: int
    us_primary_exchanges: list[str]
    allowed_share_types: list[str]
    min_breadth: int


@dataclass(frozen=True)
class SignalCfg:
    market_symbol: str
    lookback_sessions: int
    skip_sessions: int
    beta_window_sessions: int
    use_log_returns: bool


@dataclass(frozen=True)
class PortfolioCfg:
    n_deciles: int
    long_decile: int
    vol_window_sessions: int
    max_weight: float
    rebalance_frequency: str
    execution: str
    execution_fallback: str
    open_reliability_field: str
    initial_capital_usd: float


@dataclass(frozen=True)
class CostsCfg:
    spread_bps: float
    impact_k: float
    commission_per_share: float
    sec_fee_per_share_sale: float
    finra_taf_per_share_sale: float
    stress_multiplier: float


@dataclass(frozen=True)
class WalkForwardCfg:
    in_sample_months: int
    oos_months: int
    step_months: int


@dataclass(frozen=True)
class RegimesCfg:
    trend_ma_sessions: int
    vol_window_sessions: int
    vol_split: str
    definitions: list[str]


@dataclass(frozen=True)
class StressCfg:
    momentum_crash_periods: dict[str, tuple[date, date]]


@dataclass(frozen=True)
class GatesCfg:
    n_trials: int
    min_sharpe: float
    max_pvalue: float
    min_dsr: float
    min_oos_sharpe: float
    min_positive_fraction: float
    max_cv: float
    min_all_positive: bool
    min_regime_sharpe: float
    min_passing_regimes: int
    min_cumulative_return: float
    max_drawdown_allowed: float
    periods: int


@dataclass(frozen=True)
class TrialRegistryCfg:
    n_trials_for_dsr: int
    entries: list[dict[str, Any]]
    non_trials: list[str]


@dataclass(frozen=True)
class SelectionRulesCfg:
    sharpe_margin: float
    risk_improvement_min: float
    sharpe_tolerance: float
    bootstrap_min_prob: float
    material_cost_deterioration: float


@dataclass(frozen=True)
class CombinedRulesCfg:
    primary_allocation: float
    diagnostic_allocations: list[float]
    cash_return: float
    sharpe_gain_min: float
    dd_es_worsening_max: float
    dd_es_improvement_min: float
    sharpe_reduction_max: float
    bootstrap_min_prob: float
    bootstrap_draws: int
    bootstrap_seed: int


@dataclass(frozen=True)
class AmbiguityCfg:
    bootstrap_prob_band: tuple[float, float]
    margin_band: float


@dataclass(frozen=True)
class HoldoutCfg:
    signoff_required: bool
    signoff_path: str


@dataclass(frozen=True)
class DatasetCfg:
    qualification_required: bool


@dataclass(frozen=True)
class S3PocManifest:
    schema_version: str
    poc_id: str
    issue: int
    sha256: str
    source_path: str
    splits: SplitsCfg
    universe: UniverseCfg
    signal: SignalCfg
    portfolio: PortfolioCfg
    costs: CostsCfg
    walkforward: WalkForwardCfg
    regimes: RegimesCfg
    stress: StressCfg
    gates: GatesCfg
    trial_registry: TrialRegistryCfg
    selection_rules: SelectionRulesCfg
    combined_rules: CombinedRulesCfg
    ambiguity: AmbiguityCfg
    holdout: HoldoutCfg
    dataset: DatasetCfg

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["splits"] = {k: v.isoformat() for k, v in asdict(self.splits).items()}
        d["stress"]["momentum_crash_periods"] = {
            name: [a.isoformat(), b.isoformat()]
            for name, (a, b) in self.stress.momentum_crash_periods.items()
        }
        d["ambiguity"]["bootstrap_prob_band"] = list(self.ambiguity.bootstrap_prob_band)
        return d


_DATE_FIELDS = {"dev_sample_end", "holdout_start", "holdout_end", "data_excluded_after"}


def _build(section_name: str, cls: type, raw: dict[str, Any]) -> Any:
    """Costruisce una sezione tipizzata rifiutando chiavi sconosciute o tipi errati."""
    if not isinstance(raw, dict):
        raise ManifestError(f"sezione '{section_name}' non e' una mappa")
    expected = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = set(raw) - expected
    if unknown:
        raise ManifestError(f"chiavi sconosciute in '{section_name}': {sorted(unknown)}")
    missing = expected - set(raw)
    if missing:
        raise ManifestError(f"chiavi mancanti in '{section_name}': {sorted(missing)}")

    # con `from __future__ import annotations` le annotazioni sono stringhe
    _SCALARS = {"bool": bool, "int": int, "float": float}

    kwargs: dict[str, Any] = {}
    for name, value in raw.items():
        annotation = cls.__dataclass_fields__[name].type
        if name in _DATE_FIELDS:
            value = _as_date(section_name, name, value)
        elif annotation == "bool":
            if not isinstance(value, bool):
                raise ManifestError(f"{section_name}.{name} deve essere booleano")
        elif annotation == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ManifestError(f"{section_name}.{name} deve essere un intero")
        elif annotation == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ManifestError(f"{section_name}.{name} deve essere numerico")
        kwargs[name] = value
    return cls(**kwargs)


def _as_date(section: str, name: str, value: Any) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as exc:
        raise ManifestError(f"{section}.{name} non e' una data ISO: {value!r}") from exc


_TOP_LEVEL = (
    "schema_version", "poc_id", "issue", "splits", "universe", "signal", "portfolio",
    "costs", "walkforward", "regimes", "stress", "gates", "trial_registry",
    "selection_rules", "combined_rules", "ambiguity", "holdout", "dataset",
)


def load_manifest(path: Path | str) -> S3PocManifest:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ManifestError(f"manifest {path} non e' una mappa YAML")

    unknown = set(raw) - set(_TOP_LEVEL)
    if unknown:
        raise ManifestError(f"chiavi di primo livello sconosciute: {sorted(unknown)}")
    missing = set(_TOP_LEVEL) - set(raw)
    if missing:
        raise ManifestError(f"sezioni mancanti: {sorted(missing)}")

    # trial_registry: struttura libera ma conteggio coerente
    tr_raw = raw["trial_registry"]
    entries = tr_raw.get("entries")
    if not isinstance(entries, list) or not all(isinstance(e, dict) and "id" in e for e in entries):
        raise ManifestError("trial_registry.entries deve essere una lista di mappe con 'id'")
    if tr_raw.get("n_trials_for_dsr") != len(entries):
        raise ManifestError("trial_registry.n_trials_for_dsr deve equalere len(entries)")
    registry = TrialRegistryCfg(
        n_trials_for_dsr=tr_raw["n_trials_for_dsr"],
        entries=entries,
        non_trials=list(tr_raw.get("non_trials", [])),
    )

    stress_raw = raw["stress"]
    crash_periods = {
        name: (_as_date("stress", name, bounds[0]), _as_date("stress", name, bounds[1]))
        for name, bounds in stress_raw["momentum_crash_periods"].items()
    }

    amb_raw = raw["ambiguity"]
    band = amb_raw["bootstrap_prob_band"]
    if not isinstance(band, list) or len(band) != 2 or band[0] >= band[1]:
        raise ManifestError("ambiguity.bootstrap_prob_band deve essere [min, max] con min < max")

    return S3PocManifest(
        schema_version=str(raw["schema_version"]),
        poc_id=str(raw["poc_id"]),
        issue=int(raw["issue"]),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_path=str(path),
        splits=_build("splits", SplitsCfg, raw["splits"]),
        universe=_build("universe", UniverseCfg, raw["universe"]),
        signal=_build("signal", SignalCfg, raw["signal"]),
        portfolio=_build("portfolio", PortfolioCfg, raw["portfolio"]),
        costs=_build("costs", CostsCfg, raw["costs"]),
        walkforward=_build("walkforward", WalkForwardCfg, raw["walkforward"]),
        regimes=_build("regimes", RegimesCfg, raw["regimes"]),
        stress=StressCfg(momentum_crash_periods=crash_periods),
        gates=_build("gates", GatesCfg, raw["gates"]),
        trial_registry=registry,
        selection_rules=_build("selection_rules", SelectionRulesCfg, raw["selection_rules"]),
        combined_rules=_build("combined_rules", CombinedRulesCfg, raw["combined_rules"]),
        ambiguity=AmbiguityCfg(
            bootstrap_prob_band=(float(band[0]), float(band[1])),
            margin_band=float(amb_raw["margin_band"]),
        ),
        holdout=_build("holdout", HoldoutCfg, raw["holdout"]),
        dataset=_build("dataset", DatasetCfg, raw["dataset"]),
    )
