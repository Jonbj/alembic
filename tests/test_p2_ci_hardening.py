"""P2-01 CI Hardening — structural tests for the CI pipeline.

These tests verify that the GitHub Actions workflow contains all required
quality gates. They fail RED until ci.yml is updated.

Gates required:
- mypy (type checking)
- pip-audit or equivalent (dependency vulnerability scan)
- gitleaks or equivalent (secret scan)
- pytest --cov (coverage enforcement using .coveragerc)
"""
from __future__ import annotations

from pathlib import Path
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS_DIR = _ROOT / ".github" / "workflows"


def _combined_workflow_text() -> str:
    if not _WORKFLOWS_DIR.exists():
        return ""
    files = list(_WORKFLOWS_DIR.glob("*.yml")) + list(_WORKFLOWS_DIR.glob("*.yaml"))
    return "\n".join(p.read_text() for p in files)


class TestCIHardeningMypy:

    def test_ci_workflow_runs_mypy(self):
        """CI workflow must invoke mypy for type checking."""
        if not _WORKFLOWS_DIR.exists():
            pytest.skip("No .github/workflows directory")

        combined = _combined_workflow_text()
        assert "mypy" in combined, (
            "CI workflow must run mypy. "
            "Without type checking, type errors can merge silently. "
            "Add: `uv run mypy src/ --config-file pyproject.toml`"
        )


class TestCIHardeningPipAudit:

    def test_ci_workflow_runs_pip_audit_or_equivalent(self):
        """CI workflow must run pip-audit, safety, or trivy for dependency scanning."""
        if not _WORKFLOWS_DIR.exists():
            pytest.skip("No .github/workflows directory")

        combined = _combined_workflow_text().lower()
        has_audit = any(tool in combined for tool in ("pip-audit", "safety", "trivy"))
        assert has_audit, (
            "CI workflow must include a dependency vulnerability scan. "
            "Add pip-audit: `uv run pip-audit --strict` (continue-on-error: true). "
            "Without this, known CVEs in dependencies go undetected."
        )


class TestCIHardeningSecretScan:

    def test_ci_workflow_runs_secret_scan(self):
        """CI workflow must run a secret scanner (gitleaks, detect-secrets, or trufflehog)."""
        if not _WORKFLOWS_DIR.exists():
            pytest.skip("No .github/workflows directory")

        combined = _combined_workflow_text().lower()
        has_scan = any(tool in combined for tool in ("gitleaks", "detect-secrets", "trufflehog"))
        assert has_scan, (
            "CI workflow must include a secret scan step. "
            "Without it, accidentally committed secrets are not detected on PR. "
            "Add gitleaks/gitleaks-action@v2 with a .gitleaks.toml allowlist."
        )


class TestCIHardeningCoverage:

    def test_ci_workflow_runs_coverage(self):
        """CI workflow must run pytest with --cov to measure coverage."""
        if not _WORKFLOWS_DIR.exists():
            pytest.skip("No .github/workflows directory")

        combined = _combined_workflow_text()
        assert "--cov" in combined, (
            "CI workflow must invoke pytest with --cov. "
            "The .coveragerc fail_under=60 threshold is useless if coverage is never collected. "
            "Add: pytest --cov=src --cov-config=.coveragerc --cov-report=term-missing"
        )

    def test_ci_workflow_uses_coveragerc(self):
        """CI workflow must reference .coveragerc (or --cov-config) so the threshold is enforced."""
        if not _WORKFLOWS_DIR.exists():
            pytest.skip("No .github/workflows directory")

        combined = _combined_workflow_text()
        has_config = ".coveragerc" in combined or "cov-config" in combined or "cov_config" in combined
        assert has_config, (
            "CI workflow must pass --cov-config=.coveragerc to pytest. "
            "Without it, the fail_under=60 threshold in .coveragerc is ignored."
        )


class TestCIHardeningMypyConfig:

    def test_pyproject_has_mypy_section(self):
        """pyproject.toml must contain a [tool.mypy] section."""
        pyproject = _ROOT / "pyproject.toml"
        assert pyproject.exists(), "pyproject.toml must exist"

        content = pyproject.read_text()
        assert "[tool.mypy]" in content, (
            "pyproject.toml must contain a [tool.mypy] section. "
            "Without mypy configuration, running mypy would use defaults "
            "that produce excessive noise on third-party imports. "
            "Minimum: ignore_missing_imports = true, strict = false."
        )

    def test_mypy_config_has_ignore_missing_imports(self):
        """[tool.mypy] must set ignore_missing_imports to suppress stub noise."""
        pyproject = _ROOT / "pyproject.toml"
        if not pyproject.exists():
            pytest.skip("pyproject.toml not found")

        content = pyproject.read_text()
        assert "ignore_missing_imports" in content, (
            "pyproject.toml [tool.mypy] must set ignore_missing_imports = true. "
            "torch, transformers, alpaca-py have no stubs — without this flag "
            "mypy emits hundreds of errors that drown real type bugs."
        )


class TestCIHardeningGitleaksConfig:

    def test_gitleaks_config_exists(self):
        """.gitleaks.toml must exist with an allowlist for test-only credentials."""
        gitleaks_cfg = _ROOT / ".gitleaks.toml"
        assert gitleaks_cfg.exists(), (
            ".gitleaks.toml must exist in the repository root. "
            "Without an allowlist, the CI test credentials in ci.yml "
            "(test-api-key-for-ci-only, etc.) will trigger false-positive alerts "
            "and gitleaks will block every PR."
        )

    def test_gitleaks_config_has_allowlist(self):
        """.gitleaks.toml must contain an allowlist section."""
        gitleaks_cfg = _ROOT / ".gitleaks.toml"
        if not gitleaks_cfg.exists():
            pytest.skip(".gitleaks.toml not found")

        content = gitleaks_cfg.read_text().lower()
        assert "allowlist" in content, (
            ".gitleaks.toml must contain an [allowlist] section. "
            "The CI workflow has test-only credentials that must be whitelisted "
            "to avoid false positives blocking every PR."
        )
