"""Regressioni per la persistenza dei log applicativi (#407)."""

from __future__ import annotations

import selectors
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
            (
                "import sys; print('evento-forense-407', flush=True); "
                "print('errore-forense-407', file=sys.stderr, flush=True)"
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "evento-forense-407\nerrore-forense-407\n"
    giorno = datetime.now(UTC).date().isoformat()
    assert (tmp_path / f"worker-{giorno}.log").read_text() == result.stdout


def test_il_runner_elimina_solo_i_log_del_servizio_oltre_sessanta_giorni(
    tmp_path: Path,
):
    giorno_scaduto = (datetime.now(UTC).date() - timedelta(days=61)).isoformat()
    worker_scaduto = tmp_path / f"worker-{giorno_scaduto}.log"
    api_scaduto = tmp_path / f"api-{giorno_scaduto}.log"
    worker_scaduto.write_text("vecchio worker\n")
    api_scaduto.write_text("vecchia api\n")

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
            "raise SystemExit(17)",
        ],
        check=False,
    )

    assert result.returncode == 17
    assert not worker_scaduto.exists()
    assert api_scaduto.exists()


def test_il_runner_non_trattiene_l_output_finche_il_servizio_termina(tmp_path: Path):
    process = subprocess.Popen(
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
            "import time; print('subito', flush=True); time.sleep(5)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    try:
        assert selector.select(timeout=1), "l'output e' rimasto bloccato nel runner"
        assert process.stdout.readline() == "subito\n"
    finally:
        process.terminate()
        process.wait(timeout=2)


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
