"""Regression tests for observable failures in the two observation cron scripts."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "daily_alpha_miss_analysis.sh",
    "daily_analysis.sh",
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _run_with_failing_claude(tmp_path: Path, script_name: str) -> tuple[subprocess.CompletedProcess[str], str, str]:
    project = tmp_path / "project"
    scripts_dir = project / "scripts"
    bin_dir = tmp_path / "bin"
    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir()
    (project / "docs" / "evidence" / "dossier").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / script_name, scripts_dir / script_name)

    _write_executable(
        bin_dir / "claude",
        "#!/usr/bin/env bash\n"
        "printf 'output iniziale\\nCODA-ERRORE-CLAUDE\\n'\n"
        "exit 23\n",
    )
    _write_executable(
        bin_dir / "curl",
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$TELEGRAM_CAPTURE\"\n",
    )
    _write_executable(
        bin_dir / "uv",
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == 'run python3 -' ]]; then\n"
        "    printf '2026-08-06\\n'\n"
        "fi\n",
    )

    telegram_capture = tmp_path / "telegram.log"
    env = os.environ.copy()
    env.update(
        {
            "ALEMBIC_API_KEY": "test-admin-key",
            "ALPACA_API_KEY": "test-alpaca-key",
            "ALPACA_SECRET_KEY": "test-alpaca-secret",
            "HOME": str(tmp_path / "home"),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "test-chat",
            "TELEGRAM_CAPTURE": str(telegram_capture),
        }
    )
    result = subprocess.run(
        ["bash", str(scripts_dir / script_name)],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    logs = list((project / "logs").glob("*.log"))
    assert len(logs) == 1
    return result, logs[0].read_text(), telegram_capture.read_text()


@pytest.mark.parametrize("script_name", SCRIPTS)
def test_claude_failure_is_logged_alerted_and_preserves_exit_code(tmp_path: Path, script_name: str):
    result, log, telegram = _run_with_failing_claude(tmp_path, script_name)

    assert result.returncode == 23
    assert "CODA-ERRORE-CLAUDE" in log
    assert "codice 23" in log
    assert "CODA-ERRORE-CLAUDE" in telegram
    assert "codice 23" in telegram


def test_forensic_error_before_header_is_persisted(tmp_path: Path):
    project = tmp_path / "project"
    scripts_dir = project / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "daily_analysis.sh", scripts_dir / "daily_analysis.sh")

    env = os.environ.copy()
    env.pop("ALEMBIC_API_KEY", None)
    env["HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        ["bash", str(scripts_dir / "daily_analysis.sh")],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    logs = list((project / "logs").glob("daily_analysis_*.log"))
    assert len(logs) == 1
    assert "ALEMBIC_API_KEY" in logs[0].read_text()


def test_alpha_calendar_error_before_header_is_persisted(tmp_path: Path):
    project = tmp_path / "project"
    scripts_dir = project / "scripts"
    bin_dir = tmp_path / "bin"
    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy2(
        ROOT / "scripts" / "daily_alpha_miss_analysis.sh",
        scripts_dir / "daily_alpha_miss_analysis.sh",
    )
    _write_executable(
        bin_dir / "uv",
        "#!/usr/bin/env bash\n"
        "printf 'CALENDARIO-NON-DISPONIBILE\\n' >&2\n"
        "exit 17\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{bin_dir}:{env['PATH']}",
        }
    )
    result = subprocess.run(
        ["bash", str(scripts_dir / "daily_alpha_miss_analysis.sh")],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    logs = list((project / "logs").glob("alpha_miss_analysis_*.log"))
    assert len(logs) == 1
    log = logs[0].read_text()
    assert "CALENDARIO-NON-DISPONIBILE" in log
    assert "codice 17" in log


@pytest.mark.parametrize("script_name", SCRIPTS)
def test_whole_script_redirect_starts_before_environment_setup(script_name: str):
    source = (ROOT / "scripts" / script_name).read_text()

    assert source.index('exec >>"$LOG_FILE" 2>&1') < source.index(
        'if [[ -f "$PROJECT_DIR/.env" ]]'
    )


@pytest.mark.parametrize(
    ("script_name", "expected_add"),
    (
        (
            "daily_alpha_miss_analysis.sh",
            'git add docs/evidence/findings.json docs/evidence/market_daily.jsonl "__REPORT_FILE__"',
        ),
        (
            "daily_analysis.sh",
            'git add docs/evidence/findings.json "__REPORT_FILE__"',
        ),
    ),
)
def test_report_is_staged_in_the_same_commit_as_its_ledger(script_name: str, expected_add: str):
    source = (ROOT / "scripts" / script_name).read_text()

    assert expected_add in source
