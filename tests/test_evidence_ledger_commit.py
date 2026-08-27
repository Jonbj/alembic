"""Tests per il commit deterministico del ledger di osservazione (#336).

Il cron alpha-miss gira nella working tree principale del repo, che spesso e'
parcheggiata sul branch di un altro agente: la guardia nel prompt rifiutava il
commit e il ledger restava solo su disco. Qui il commit avviene in una worktree
dedicata appuntata su main, quindi il branch della tree principale non conta.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
REAL_GIT = shutil.which("git") or "/usr/bin/git"
HELPER = ROOT / "scripts" / "commit_evidence_ledger.sh"
REPORT = "docs/ALPHA_MISS_REPORT_2026-08-26.md"
LEDGER = "docs/evidence/findings.json"
JSONL = "docs/evidence/market_daily.jsonl"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return result.stdout


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture()
def repo(tmp_path: Path) -> dict:
    """Remote bare + clone principale parcheggiato su un branch di lavoro."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)],
        check=True,
        capture_output=True,
    )
    project = tmp_path / "project"
    subprocess.run(
        ["git", "clone", str(remote), str(project)], check=True, capture_output=True
    )
    _git(project, "config", "user.email", "cron@alembic.test")
    _git(project, "config", "user.name", "Cron Alembic")

    _write(project / LEDGER, '{"findings": []}\n')
    _write(project / JSONL, '{"data": "2026-08-25"}\n')
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "base")
    _git(project, "push", "origin", "main")

    # la condizione del difetto: la tree principale sta su un branch altrui
    _git(project, "checkout", "-b", "agent/issue-999")

    (project / "scripts").mkdir(exist_ok=True)
    shutil.copy2(HELPER, project / "scripts" / HELPER.name)
    return {"remote": remote, "project": project, "tmp": tmp_path}


def _dirty_the_ledger(project: Path) -> None:
    _write(project / LEDGER, '{"findings": ["F-001"]}\n')
    with (project / JSONL).open("a") as handle:
        handle.write('{"data": "2026-08-26"}\n')
    _write(project / REPORT, "# Alpha miss 2026-08-26\n")


def _run_helper(repo: dict, *paths: str, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "EVIDENCE_WORKTREE": str(repo["tmp"] / "wt-evidence"),
            "EVIDENCE_PENDING_FILE": str(repo["tmp"] / "pending.txt"),
            "HOME": str(repo["tmp"] / "home"),
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [
            "bash",
            str(repo["project"] / "scripts" / HELPER.name),
            "--message",
            "evidence: ledger 2026-08-26",
            *paths,
        ],
        cwd=repo["project"],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _remote_file(remote: Path, path: str) -> str:
    return _git(remote, "show", f"main:{path}")


def _status_line(output: str) -> str:
    lines = [ln for ln in output.splitlines() if ln.startswith("GIT_STATUS=")]
    assert lines, f"nessuna riga GIT_STATUS nell'output:\n{output}"
    return lines[-1]


def test_commits_and_pushes_even_if_main_tree_is_on_a_feature_branch(repo):
    _dirty_the_ledger(repo["project"])

    result = _run_helper(repo, LEDGER, JSONL, REPORT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _status_line(result.stdout) == "GIT_STATUS=pushed"
    assert _remote_file(repo["remote"], REPORT) == "# Alpha miss 2026-08-26\n"
    assert "F-001" in _remote_file(repo["remote"], LEDGER)
    assert "2026-08-26" in _remote_file(repo["remote"], JSONL)


def test_main_working_tree_is_left_untouched(repo):
    project = repo["project"]
    _dirty_the_ledger(project)

    _run_helper(repo, LEDGER, JSONL, REPORT)

    assert _git(project, "rev-parse", "--abbrev-ref", "HEAD").strip() == "agent/issue-999"
    # i file restano sul disco della tree principale, ancora non committati li'
    assert (project / REPORT).read_text() == "# Alpha miss 2026-08-26\n"
    assert "F-001" in (project / LEDGER).read_text()


def test_push_rejected_is_retried_after_resync(repo):
    """Il remoto avanza tra il fetch e il push: un retry solo, senza forzare."""
    project, remote, tmp = repo["project"], repo["remote"], repo["tmp"]
    side = tmp / "side"
    subprocess.run(["git", "clone", str(remote), str(side)], check=True, capture_output=True)
    _git(side, "config", "user.email", "altro@alembic.test")
    _git(side, "config", "user.name", "Altro Agente")
    _write(side / "docs/altro.md", "lavoro concorrente\n")
    _git(side, "add", "-A")
    _git(side, "commit", "-m", "concorrente")

    bin_dir = tmp / "bin"
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        'for arg in "$@"; do\n'
        '    if [[ "$arg" == push && ! -f "$INJECT_FLAG" ]]; then\n'
        '        touch "$INJECT_FLAG"\n'
        f'        {REAL_GIT} -C {side} push origin main >/dev/null 2>&1\n'
        "    fi\n"
        "done\n"
        f'exec {REAL_GIT} "$@"\n',
    )
    _dirty_the_ledger(project)

    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "INJECT_FLAG": str(tmp / "injected"),
    }
    result = _run_helper(repo, LEDGER, JSONL, REPORT, extra_env=env)

    assert (tmp / "injected").exists(), "il primo push doveva trovare il remoto avanzato"
    assert "push rifiutato al tentativo 1" in result.stdout
    assert _status_line(result.stdout) == "GIT_STATUS=pushed"
    assert _remote_file(remote, REPORT) == "# Alpha miss 2026-08-26\n"
    # il lavoro concorrente non e' stato sovrascritto
    assert _remote_file(remote, "docs/altro.md") == "lavoro concorrente\n"


def _failing_push_bin(tmp: Path) -> Path:
    bin_dir = tmp / "bin-nopush"
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        'for arg in "$@"; do\n'
        '    if [[ "$arg" == push ]]; then\n'
        "        echo 'push rifiutato (test)' >&2\n"
        "        exit 1\n"
        "    fi\n"
        "done\n"
        f'exec {REAL_GIT} "$@"\n',
    )
    return bin_dir


def test_push_failure_reports_committed_not_pushed_and_carries_over(repo):
    project, remote, tmp = repo["project"], repo["remote"], repo["tmp"]
    _dirty_the_ledger(project)

    env = {"PATH": f"{_failing_push_bin(tmp)}:{os.environ['PATH']}"}
    first = _run_helper(repo, LEDGER, JSONL, REPORT, extra_env=env)

    assert first.returncode != 0
    assert _status_line(first.stdout) == "GIT_STATUS=committed_not_pushed"
    pending = (tmp / "pending.txt").read_text()
    assert REPORT in pending

    # giro successivo: il report di ieri non e' fra i path richiesti, ma la lista
    # dei pendenti lo riporta comunque su main.
    second = _run_helper(repo, LEDGER, JSONL)

    assert _status_line(second.stdout) == "GIT_STATUS=pushed"
    assert _remote_file(remote, REPORT) == "# Alpha miss 2026-08-26\n"
    assert (tmp / "pending.txt").read_text().strip() == ""


def test_nothing_to_commit_is_its_own_status(repo):
    result = _run_helper(repo, LEDGER, JSONL)

    assert result.returncode == 0
    assert _status_line(result.stdout) == "GIT_STATUS=nothing_to_commit"


def test_shrinking_an_append_only_jsonl_is_refused(repo):
    """Una copia su disco piu' vecchia di main non deve troncare il ledger."""
    project, remote = repo["project"], repo["remote"]
    _dirty_the_ledger(project)
    _run_helper(repo, LEDGER, JSONL, REPORT)
    before = _remote_file(remote, JSONL)

    # regressione simulata: il file su disco perde una riga
    _write(project / JSONL, '{"data": "2026-08-25"}\n')

    result = _run_helper(repo, JSONL)

    assert result.returncode != 0
    assert _status_line(result.stdout) == "GIT_STATUS=not_committed"
    assert _remote_file(remote, JSONL) == before


def test_missing_worktree_is_recreated(repo):
    project, tmp = repo["project"], repo["tmp"]
    _dirty_the_ledger(project)
    _run_helper(repo, LEDGER, JSONL, REPORT)

    shutil.rmtree(tmp / "wt-evidence")
    _write(project / REPORT, "# Alpha miss 2026-08-26 (v2)\n")

    result = _run_helper(repo, REPORT)

    assert _status_line(result.stdout) == "GIT_STATUS=pushed"
    assert _remote_file(repo["remote"], REPORT) == "# Alpha miss 2026-08-26 (v2)\n"


# --- cablaggio del cron alpha-miss (#336) ----------------------------------

CRON = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"
ECON = "docs/evidence/economic_pnl.json"


def _run_cron(repo: dict, extra_path: Path | None = None) -> tuple[subprocess.CompletedProcess[str], str, str]:
    project, tmp = repo["project"], repo["tmp"]
    shutil.copy2(CRON, project / "scripts" / CRON.name)
    (project / "docs" / "evidence" / "dossier").mkdir(parents=True, exist_ok=True)
    bin_dir = tmp / "bin-cron"

    _write_executable(
        bin_dir / "uv",
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == 'run python3 -' ]]; then\n"
        "    printf '2026-08-26\\n'\n"
        "fi\n"
        'if [[ "$*" == *alpha_miner_dossier.py* ]]; then\n'
        "    printf '{\"dossier\": \"2026-08-26\"}\\n' > docs/evidence/dossier/2026-08-26.json\n"
        "fi\n"
        'if [[ "$*" == *economic_pnl_scoreboard.py* ]]; then\n'
        "    printf '{\"aggiornato\": \"2026-08-26\"}\\n' > docs/evidence/economic_pnl.json\n"
        "fi\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "claude",
        "#!/usr/bin/env bash\n"
        "printf 'Executive summary fittizio\\n'\n"
        "printf '%s\\n' '{\"findings\": [\"F-001\"]}' > docs/evidence/findings.json\n"
        "printf '%s\\n' '{\"data\": \"2026-08-26\"}' >> docs/evidence/market_daily.jsonl\n"
        f"printf '# Alpha miss 2026-08-26\\n' > {REPORT}\n",
    )
    _write_executable(
        bin_dir / "curl",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$TELEGRAM_CAPTURE\"\n",
    )

    telegram = tmp / "telegram.log"
    env = os.environ.copy()
    env.update(
        {
            "ALPACA_API_KEY": "k",
            "ALPACA_SECRET_KEY": "s",
            "HOME": str(tmp / "home"),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "TELEGRAM_BOT_TOKEN": "t",
            "TELEGRAM_CHAT_ID": "c",
            "TELEGRAM_CAPTURE": str(telegram),
            "EVIDENCE_WORKTREE": str(tmp / "wt-evidence"),
            "EVIDENCE_PENDING_FILE": str(tmp / "pending.txt"),
        }
    )
    if extra_path is not None:
        env["PATH"] = f"{extra_path}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(project / "scripts" / CRON.name)],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    logs = list((project / "logs").glob("alpha_miss_analysis_*.log"))
    assert len(logs) == 1
    return result, logs[0].read_text(), telegram.read_text()


def test_cron_commits_the_ledger_from_a_feature_branch(repo):
    shutil.copy2(HELPER, repo["project"] / "scripts" / HELPER.name)

    result, log, telegram = _run_cron(repo)

    assert result.returncode == 0, log[-2000:]
    assert log.strip().splitlines()[-1] == "GIT_STATUS=pushed"
    assert _remote_file(repo["remote"], REPORT) == "# Alpha miss 2026-08-26\n"
    assert "F-001" in _remote_file(repo["remote"], LEDGER)
    assert "2026-08-26" in _remote_file(repo["remote"], ECON)
    assert "2026-08-26" in _remote_file(repo["remote"], "docs/evidence/dossier/2026-08-26.json")
    assert "GIT_STATUS=pushed" in telegram


def test_cron_alerts_when_the_ledger_does_not_reach_main(repo):
    shutil.copy2(HELPER, repo["project"] / "scripts" / HELPER.name)
    _, log, telegram = _run_cron(repo, extra_path=_failing_push_bin(repo["tmp"]))

    assert log.strip().splitlines()[-1] == "GIT_STATUS=committed_not_pushed"
    assert "committed_not_pushed" in telegram
    assert "⚠️" in telegram or "🚨" in telegram


def test_cron_prompt_no_longer_asks_the_session_to_commit():
    source = CRON.read_text()

    assert "git commit -m" not in source
    assert "atteso main" not in source


def test_cron_hands_report_and_ledgers_to_the_helper_in_one_commit():
    source = CRON.read_text()

    assert "scripts/commit_evidence_ledger.sh" in source
    block = source.rsplit("COMMIT_PATHS=(", 1)[1].split("commit_evidence_ledger.sh", 1)[0]
    for path in (
        "docs/evidence/findings.json",
        "docs/evidence/market_daily.jsonl",
        ECON,
        "REPORT_FILE",
        "DOSSIER_FILE",
    ):
        assert path in block


def test_broken_worktree_registration_is_rebuilt(repo):
    project, tmp = repo["project"], repo["tmp"]
    _dirty_the_ledger(project)
    _run_helper(repo, LEDGER, JSONL, REPORT)

    # worktree registrata ma inservibile: il puntatore al repo non risolve piu'
    (tmp / "wt-evidence" / ".git").write_text("gitdir: /percorso/che/non/esiste\n")
    _write(project / REPORT, "# Alpha miss 2026-08-26 (v3)\n")

    result = _run_helper(repo, REPORT)

    assert _status_line(result.stdout) == "GIT_STATUS=pushed"
    assert _remote_file(repo["remote"], REPORT) == "# Alpha miss 2026-08-26 (v3)\n"
