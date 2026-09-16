"""Helper condivisi dai test del POC S3 (#84).

I manifest fixture derivano sempre da quello di produzione con override
annidati: i test esercitano le regole, la produzione resta congelata.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_MANIFEST = REPO_ROOT / "docs" / "evidence" / "S3_POC_MANIFEST_84.yaml"


def load_raw_manifest() -> dict:
    return yaml.safe_load(PRODUCTION_MANIFEST.read_text())


def write_manifest_override(tmp_path: Path, overrides: dict) -> Path:
    """Copia il manifest di produzione applicando override annidati."""
    raw = load_raw_manifest()

    def apply(target: dict, patch: dict) -> None:
        for key, value in patch.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                apply(target[key], value)
            else:
                target[key] = value

    apply(raw, overrides)
    out = tmp_path / "manifest.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False))
    return out
