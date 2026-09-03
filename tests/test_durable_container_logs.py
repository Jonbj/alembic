"""Regressioni per la persistenza dei log applicativi (#407)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
RUNNER = ROOT / "scripts" / "run_with_durable_logs.py"
SERVICES = ("api", "worker", "worker-inference", "beat")


def test_i_servizi_applicativi_scrivono_sul_log_host_persistente():
    compose = yaml.safe_load(COMPOSE.read_text())

    for service in SERVICES:
        config = compose["services"][service]
        assert f"--service {service} --" in config["command"]
        assert (
            "${ALEMBIC_DURABLE_LOG_DIR:-./logs/containers}:/var/log/alembic"
            in config["volumes"]
        )


def test_il_runner_duplica_stdout_e_conserva_il_file_giornaliero(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--service",
            "worker",
            "--log-dir",
            str(tmp_path),
            "--",
            sys.executable,
            "-c",
            "print('evento-forense-407')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "evento-forense-407\n"
    giorno = datetime.now(UTC).date().isoformat()
    assert (tmp_path / f"worker-{giorno}.log").read_text() == result.stdout


def test_il_deploy_usa_una_directory_stabile_fuori_dal_worktree_temporaneo():
    source = (ROOT / "scripts" / "deploy_reconcile.sh").read_text()

    posizione_directory = source.index(
        'ALEMBIC_DURABLE_LOG_DIR="$PROJECT_DIR/logs/containers"'
    )
    posizione_deploy = source.index('docker compose -p "$COMPOSE_PROJ" up -d')
    assert posizione_directory < posizione_deploy


def test_i_cron_indicano_i_log_persistenti_come_fonte():
    for script_name in ("daily_analysis.sh", "daily_alpha_miss_analysis.sh"):
        source = (ROOT / "scripts" / script_name).read_text()
        assert "logs/containers" in source

    forensic = (ROOT / "scripts" / "daily_analysis.sh").read_text()
    assert "docker compose logs worker --since 48h" not in forensic
