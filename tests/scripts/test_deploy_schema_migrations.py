"""The deploy reconciler must apply schema before replacing workers (#532)."""

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy_reconcile.sh"


def test_backend_deploy_migrates_after_build_before_restart():
    source = DEPLOY.read_text()

    build = source.index('docker compose -p "$COMPOSE_PROJ" build')
    migrate = source.index("scripts/apply_migrations.py")
    restart = source.index('docker compose -p "$COMPOSE_PROJ" up -d')

    assert build < migrate < restart
    assert "--bootstrap-existing-through 59" in source
    assert 'fallisci "applicazione delle migrazioni database"' in source
    assert "migrations/*" in source


def test_deploy_loads_database_url_without_exposing_unrelated_secrets():
    source = DEPLOY.read_text()

    assert "DATABASE_URL" in source
    assert "TELEGRAM_(BOT_TOKEN|CHAT_ID)|ALPACA_(API_KEY|SECRET_KEY)|DATABASE_URL" in source


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(0o755)


def test_failed_migration_does_not_restart_or_advance_deployed_sha(
    tmp_path: Path,
):
    project = tmp_path / "project"
    scripts = project / "scripts"
    logs = project / "logs"
    fake_bin = tmp_path / "home" / ".local" / "bin"
    scripts.mkdir(parents=True)
    logs.mkdir()
    fake_bin.mkdir(parents=True)
    shutil.copy2(DEPLOY, scripts / DEPLOY.name)

    old_sha = "1" * 40
    new_sha = "2" * 40
    (logs / "deployed_sha").write_text(old_sha + "\n")
    calls = tmp_path / "calls.log"

    _write_executable(
        fake_bin / "git",
        f"""#!/usr/bin/env bash
set -eu
if [[ "$1" == "rev-parse" ]]; then
    echo {new_sha}
elif [[ "$1" == "diff" ]]; then
    echo migrations/060_s4_burned_slot_metrics.sql
elif [[ "$1" == "rev-list" ]]; then
    echo 1
elif [[ "$1" == "worktree" && "$2" == "add" ]]; then
    /usr/bin/mkdir -p "$5"
fi
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -eu
echo "docker $*" >> "$CALLS_FILE"
exit 0
""",
    )
    _write_executable(
        fake_bin / "uv",
        """#!/usr/bin/env bash
set -eu
echo "migration $*" >> "$CALLS_FILE"
exit 42
""",
    )

    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": "/usr/bin:/bin",
        "CALLS_FILE": str(calls),
    }
    completed = subprocess.run(
        ["/bin/bash", str(scripts / DEPLOY.name), "--forza"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    recorded_calls = calls.read_text()
    assert " compose -p alembic build " in recorded_calls
    assert "migration run --project" in recorded_calls
    assert " compose -p alembic up " not in recorded_calls
    assert (logs / "deployed_sha").read_text() == old_sha + "\n"
