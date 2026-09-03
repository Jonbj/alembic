"""Fail-fast coverage for the test-suite database boundary."""

import os
import subprocess
import sys

import pytest


def test_pytest_refuses_a_database_without_test_name():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://trading:trading@localhost:5432/trading"

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
