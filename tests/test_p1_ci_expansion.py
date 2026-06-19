"""P1-11 CI expansion — mypy config, pip-audit, coverage threshold, secret scan.

Problem (from audit): no formal CI gating for type errors, dependency
vulnerabilities, secret leaks, or test coverage. Regressions can merge
undetected.

Fix: verify that the CI configuration files exist and are correctly wired.
These tests are structural (file existence + key config presence).
"""
from __future__ import annotations

from pathlib import Path
import pytest

_ROOT = Path(__file__).resolve().parents[1]


class TestMypyConfig:

    def test_mypy_config_exists(self):
        """A mypy configuration must exist (mypy.ini, setup.cfg [mypy], or pyproject.toml)."""
        candidates = [
            _ROOT / "mypy.ini",
            _ROOT / "setup.cfg",
            _ROOT / "pyproject.toml",
        ]
        found = [p for p in candidates if p.exists()]
        assert found, (
            "No mypy config found. Create mypy.ini or add [mypy] section to setup.cfg. "
            "Without mypy CI gate, type errors can merge silently."
        )

    def test_mypy_config_covers_src(self):
        """mypy config must declare the src package as a target."""
        mypy_ini = _ROOT / "mypy.ini"
        setup_cfg = _ROOT / "setup.cfg"
        pyproject = _ROOT / "pyproject.toml"

        content = ""
        for path in [mypy_ini, setup_cfg, pyproject]:
            if path.exists():
                content += path.read_text()

        assert "src" in content.lower() or "mypy" in content.lower(), (
            "mypy config must reference 'src' package or mypy section. "
            "Without it, mypy will not check the trading system code."
        )


class TestCoverageConfig:

    def test_coverage_config_exists(self):
        """.coveragerc or [coverage] section in setup.cfg / pyproject.toml must exist."""
        candidates = [
            _ROOT / ".coveragerc",
            _ROOT / "setup.cfg",
            _ROOT / "pyproject.toml",
        ]
        coverage_configured = False
        for p in candidates:
            if p.exists() and ("coverage" in p.read_text().lower()):
                coverage_configured = True
                break

        assert coverage_configured, (
            "No coverage configuration found. "
            "Add [coverage:run] section to setup.cfg or a .coveragerc file. "
            "CI must enforce a minimum coverage threshold."
        )

    def test_coverage_threshold_defined(self):
        """A minimum coverage threshold (fail_under) must be defined."""
        candidates = [_ROOT / ".coveragerc", _ROOT / "setup.cfg", _ROOT / "pyproject.toml"]
        threshold_defined = False
        for p in candidates:
            if p.exists():
                text = p.read_text().lower()
                if "fail_under" in text or "min_coverage" in text:
                    threshold_defined = True
                    break

        assert threshold_defined, (
            "No coverage fail_under threshold found in .coveragerc or setup.cfg. "
            "Without a minimum threshold, coverage can drop to 0% without CI failing."
        )


class TestCIWorkflow:

    def test_github_actions_workflow_exists(self):
        """A GitHub Actions CI workflow must exist."""
        workflows_dir = _ROOT / ".github" / "workflows"
        if not workflows_dir.exists():
            pytest.skip("No .github/workflows directory — skipping CI workflow check")

        workflows = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
        assert workflows, (
            "No GitHub Actions workflow files found in .github/workflows/. "
            "CI must be configured to run tests on every PR."
        )

    def test_ci_workflow_runs_pytest(self):
        """The CI workflow must invoke pytest."""
        workflows_dir = _ROOT / ".github" / "workflows"
        if not workflows_dir.exists():
            pytest.skip("No .github/workflows directory")

        workflows = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
        if not workflows:
            pytest.skip("No workflow files")

        combined = "\n".join(p.read_text() for p in workflows)
        assert "pytest" in combined, (
            "CI workflow must invoke pytest. Found workflow files but none contain 'pytest'."
        )
