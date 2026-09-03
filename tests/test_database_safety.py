"""Fail-fast coverage for the test-suite database boundary."""

import os
import subprocess
import sys

import pytest


def test_pytest_refuses_a_database_without_test_name():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://trading:trading@localhost:5432/trading"
    env.pop("GITHUB_ACTIONS", None)
    env.pop("RUNNER_ENVIRONMENT", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/workers/test_rss_ingestion.py",
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=30,
    )

    output = result.stdout + result.stderr
    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    assert "Refusing to run tests against non-test database 'trading'" in output


def test_pytest_accepts_the_ephemeral_github_hosted_database():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://trading:trading@localhost:5432/trading"
    env["GITHUB_ACTIONS"] = "true"
    env["RUNNER_ENVIRONMENT"] = "github-hosted"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/workers/test_rss_ingestion.py",
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=30,
    )

    assert result.returncode == pytest.ExitCode.OK, result.stdout + result.stderr
