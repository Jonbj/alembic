"""Contratto del runner che produce l'artefatto decisionale S3 (#84)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.s3_poc_util import write_manifest_override


@pytest.fixture
def manifest(tmp_path):
    return load_manifest(write_manifest_override(tmp_path, {
        "combined_rules": {"bootstrap_draws": 20},
    }))


def test_runner_assembla_provenance_manifest_e_decisioni(monkeypatch, manifest) -> None:
    from src.analysis.s3_poc import runner

    ds = synthetic_dataset()
    returns = pd.Series(0.001, index=ds.sessions[1:])

    def fake_evaluation(_ds, _manifest, variant, _start, _end, cost_multiplier=1.0):
        return SimpleNamespace(
            variant=variant,
            returns=returns,
            to_dict=lambda: {"variant": variant, "cost_multiplier": cost_multiplier},
        )

    monkeypatch.setattr(runner, "evaluate_variant", fake_evaluation)
    monkeypatch.setattr(runner, "select_variant", lambda *_: SimpleNamespace(
        outcome="SELECT_B", selected_variant="B", replication_required=False,
        to_dict=lambda: {"outcome": "SELECT_B", "selected_variant": "B"},
    ))
    monkeypatch.setattr(runner, "evaluate_combined", lambda *_: SimpleNamespace(
        decision_outcome="PASS", to_dict=lambda: {"decision_outcome": "PASS"},
    ))

    artifact = runner.run_poc(
        ds, manifest, returns,
        pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"),
        code_revision="test-revision",
    )

    serialized = artifact.to_dict()
    assert serialized["code_revision"] == "test-revision"
    assert serialized["manifest"]["sha256"] == manifest.sha256
    assert serialized["data_provenance"]["synthetic"] is True
    assert serialized["data_checksum"]
    assert serialized["variants"]["A"]["base"]["variant"] == "A"
    assert serialized["variants"]["B"]["cost_stress"]["cost_multiplier"] == 2.0
    assert serialized["selection"]["selected_variant"] == "B"
    assert serialized["combined"]["decision_outcome"] == "PASS"
    assert serialized["poc_outcome"] == "DECISION_BRIEF_READY"


def test_runner_rifiuta_holdout_senza_signoff(manifest) -> None:
    from src.analysis.s3_poc.runner import HoldoutNotSignedOff, run_poc

    ds = synthetic_dataset()
    with pytest.raises(HoldoutNotSignedOff, match="sign-off"):
        run_poc(
            ds, manifest, None,
            pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31"),
            code_revision="test-revision",
        )


def synthetic_dataset():
    return build_synthetic_dataset(SyntheticSpec(
        start=date(2019, 1, 1),
        end=date(2025, 12, 31),
        securities=tuple(SecuritySpec(security_id=f"S{i}") for i in range(3)),
    ))
