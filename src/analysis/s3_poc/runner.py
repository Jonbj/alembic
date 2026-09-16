"""Runner offline del POC S3 (#84): dati qualificati e manifest in, artefatto out."""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.analysis.s3_poc.combined import CombinedReport, evaluate_combined
from src.analysis.s3_poc.dataset import PitDataset, canonical_sha256, require_qualified_or_synthetic
from src.analysis.s3_poc.decision import VariantSelection, select_variant
from src.analysis.s3_poc.evaluation import evaluate_variant
from src.analysis.s3_poc.manifest import S3PocManifest


class HoldoutNotSignedOff(RuntimeError):
    """Il campione 2023--2025 e' stato richiesto prima della review indipendente."""


@dataclass(frozen=True)
class PocArtifact:
    """Artefatto versionato e JSON-serializzabile della decisione offline."""

    schema_version: str
    poc_id: str
    code_revision: str
    manifest: dict[str, Any]
    data_provenance: dict[str, Any]
    data_checksum: str
    splits: dict[str, str]
    trial_registry: dict[str, Any]
    costs: dict[str, Any]
    variants: dict[str, dict[str, dict[str, Any]]]
    selection: dict[str, Any]
    combined: dict[str, Any] | None
    poc_outcome: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _repository_revision() -> str:
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _validate_period(
    manifest: S3PocManifest, period_start: pd.Timestamp, period_end: pd.Timestamp
) -> None:
    if period_end > pd.Timestamp(manifest.splits.data_excluded_after):
        raise ValueError("il periodo richiesto supera data_excluded_after del manifest")
    if period_end <= pd.Timestamp(manifest.splits.dev_sample_end):
        return

    holdout_start = pd.Timestamp(manifest.splits.holdout_start)
    holdout_end = pd.Timestamp(manifest.splits.holdout_end)
    if period_start != holdout_start or period_end != holdout_end:
        raise ValueError("l'holdout va aperto soltanto come intervallo sigillato 2023-2025")
    if manifest.holdout.signoff_required and not Path(manifest.holdout.signoff_path).is_file():
        raise HoldoutNotSignedOff("holdout rifiutato: manca il sign-off indipendente registrato")


def _poc_outcome(selection: VariantSelection, combined: CombinedReport | None) -> str:
    if selection.selected_variant is None:
        return selection.outcome
    if combined is None:
        return "NOT_EVALUABLE"
    if combined.decision_outcome == "PASS":
        return "DECISION_BRIEF_READY"
    return combined.decision_outcome


def run_poc(
    ds: PitDataset,
    manifest: S3PocManifest,
    s1_returns: pd.Series | None,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    *,
    code_revision: str | None = None,
) -> PocArtifact:
    """Esegue A/B e il test S1+cash usando esclusivamente input congelati.

    I dati reali senza qualificazione sono rifiutati. Il holdout non puo'
    essere chiesto a pezzi e richiede il sign-off indipendente gia' registrato.
    Il risultato resta un artefatto di ricerca: non chiama nessun registry o
    percorso operativo.
    """
    period_start, period_end = pd.Timestamp(period_start), pd.Timestamp(period_end)
    _validate_period(manifest, period_start, period_end)
    require_qualified_or_synthetic(ds, manifest.dataset.qualification_required)

    base_a = evaluate_variant(ds, manifest, "A", period_start, period_end)
    base_b = evaluate_variant(ds, manifest, "B", period_start, period_end)
    stress_a = evaluate_variant(
        ds, manifest, "A", period_start, period_end, manifest.costs.stress_multiplier
    )
    stress_b = evaluate_variant(
        ds, manifest, "B", period_start, period_end, manifest.costs.stress_multiplier
    )
    selection = select_variant(base_a, base_b, manifest)
    selected = {"A": base_a, "B": base_b}.get(selection.selected_variant)
    combined = evaluate_combined(s1_returns, selected.returns, manifest) if selected else None

    return PocArtifact(
        schema_version="1",
        poc_id=manifest.poc_id,
        code_revision=code_revision or _repository_revision(),
        manifest={"source_path": manifest.source_path, "sha256": manifest.sha256},
        data_provenance=ds.provenance.to_dict(),
        data_checksum=canonical_sha256(ds),
        splits={
            "dev_sample_end": manifest.splits.dev_sample_end.isoformat(),
            "holdout_start": manifest.splits.holdout_start.isoformat(),
            "holdout_end": manifest.splits.holdout_end.isoformat(),
        },
        trial_registry={
            "n_trials_for_dsr": manifest.trial_registry.n_trials_for_dsr,
            "entries": manifest.trial_registry.entries,
            "non_trials": manifest.trial_registry.non_trials,
        },
        costs=asdict(manifest.costs),
        variants={
            "A": {"base": base_a.to_dict(), "cost_stress": stress_a.to_dict()},
            "B": {"base": base_b.to_dict(), "cost_stress": stress_b.to_dict()},
        },
        selection=selection.to_dict(),
        combined=combined.to_dict() if combined else None,
        poc_outcome=_poc_outcome(selection, combined),
    )
