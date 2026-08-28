"""Tests per il commit deterministico del ledger di osservazione (#336).

Il cron alpha-miss gira nella working tree principale del repo, che spesso e'
parcheggiata sul branch di un altro agente: la guardia nel prompt rifiutava il
commit e il ledger restava solo su disco. Qui il commit avviene in una worktree
dedicata appuntata su main, quindi il branch della tree principale non conta.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REAL_GIT = shutil.which("git") or "/usr/bin/git"
HELPER = ROOT / "scripts" / "commit_evidence_ledger.sh"
MERGER = ROOT / "scripts" / "merge_evidence_findings.py"
JSONL_MERGER = ROOT / "scripts" / "merge_evidence_jsonl.py"
REFRESHER = ROOT / "scripts" / "refresh_evidence_ledger.sh"
SCRIPTS = (HELPER, MERGER, JSONL_MERGER, REFRESHER)
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

    _write(
        project / LEDGER,
        json.dumps(
            {"schema_version": 1, "prossimo_id": 1, "findings": []}, indent=2
        ) + "\n",
    )
    _write(project / JSONL, '{"data": "2026-08-25"}\n')
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "base")
    _git(project, "push", "origin", "main")

    # la condizione del difetto: la tree principale sta su un branch altrui
    _git(project, "checkout", "-b", "agent/issue-999")

    (project / "scripts").mkdir(exist_ok=True)
    for script in SCRIPTS:
        shutil.copy2(script, project / "scripts" / script.name)
    return {"remote": remote, "project": project, "tmp": tmp_path}


def _dirty_the_ledger(project: Path) -> None:
    _write(
        project / LEDGER,
        json.dumps(
            {
                "schema_version": 1,
                "prossimo_id": 2,
                "findings": [
                    {
                        "id": "F-001",
                        "titolo": "Finding di test",
                        "occorrenze": [
                            {
                                "data": "2026-08-26",
                                "costo_usd": 1.0,
                                "nota": "test",
                                "fonte": "REPORT_TEST.md",
                            }
                        ],
                        "costo_cumulato_usd": 1.0,
                        "occorrenze_non_stimate": 0,
                    }
                ],
            },
            indent=2,
        ) + "\n",
    )
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
    _write(
        side / LEDGER,
        json.dumps(
            {
                "schema_version": 1,
                "prossimo_id": 3,
                "findings": [
                    {
                        "id": "F-002",
                        "titolo": "Finding concorrente",
                        "occorrenze": [
                            {
                                "data": "2026-08-26",
                                "costo_usd": 2.0,
                                "nota": "pubblicato mentre il cron pusha",
                                "fonte": "REPORT_CONCORRENTE.md",
                            }
                        ],
                        "costo_cumulato_usd": 2.0,
                        "occorrenze_non_stimate": 0,
                    }
                ],
            },
            indent=2,
        ) + "\n",
    )
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
    findings = json.loads(_remote_file(remote, LEDGER))["findings"]
    assert [finding["id"] for finding in findings] == ["F-002", "F-001"]


def test_remote_findings_occurrence_is_preserved_when_source_branch_is_stale(repo):
    """Una nuova occorrenza su main non deve sparire copiando lo snapshot locale."""
    project, remote, tmp = repo["project"], repo["remote"], repo["tmp"]
    base_occurrence = {
        "data": "2026-08-25",
        "costo_usd": 10.0,
        "nota": "base",
        "fonte": "REPORT_BASE.md",
    }
    local_occurrence = {
        "data": "2026-08-26",
        "costo_usd": 20.0,
        "nota": "cron alpha-miss",
        "fonte": "REPORT_ALPHA.md",
    }
    remote_occurrence = {
        "data": "2026-08-26",
        "costo_usd": 30.0,
        "nota": "analisi concorrente gia' su main",
        "fonte": "REPORT_CONCORRENTE.md",
    }

    def ledger(*occurrences: dict) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "prossimo_id": 2,
                "findings": [
                    {
                        "id": "F-001",
                        "titolo": "Copertura news bassa",
                        "tipo": "osservazione",
                        "occorrenze": list(occurrences),
                        "costo_cumulato_usd": sum(
                            occurrence["costo_usd"] for occurrence in occurrences
                        ),
                        "occorrenze_non_stimate": 0,
                    }
                ],
            },
            indent=2,
        ) + "\n"

    # La feature branch conserva lo snapshot da cui il cron e' partito e vi
    # aggiunge la propria occorrenza.
    _write(project / LEDGER, ledger(base_occurrence, local_occurrence))

    # Nel frattempo main acquisisce un'altra occorrenza sullo stesso finding.
    side = tmp / "side-findings"
    subprocess.run(["git", "clone", str(remote), str(side)], check=True, capture_output=True)
    _git(side, "config", "user.email", "altro@alembic.test")
    _git(side, "config", "user.name", "Altro Agente")
    _write(side / LEDGER, ledger(base_occurrence, remote_occurrence))
    _git(side, "add", LEDGER)
    _git(side, "commit", "-m", "evidence concorrente")
    _git(side, "push", "origin", "main")

    result = _run_helper(repo, LEDGER)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _status_line(result.stdout) == "GIT_STATUS=pushed"
    merged = json.loads(_remote_file(remote, LEDGER))["findings"][0]
    assert merged["occorrenze"] == [
        base_occurrence,
        remote_occurrence,
        local_occurrence,
    ]
    assert merged["costo_cumulato_usd"] == 60.0


def test_conflicting_change_to_published_occurrence_is_refused(tmp_path):
    """Stessa data/fonte con contenuto diverso non e' una nuova occorrenza."""
    canonical = {
        "schema_version": 1,
        "prossimo_id": 2,
        "findings": [
            {
                "id": "F-001",
                "titolo": "Copertura news bassa",
                "occorrenze": [
                    {
                        "data": "2026-08-26",
                        "costo_usd": 10.0,
                        "nota": "gia' pubblicata",
                        "fonte": "REPORT.md",
                    }
                ],
                "costo_cumulato_usd": 10.0,
                "occorrenze_non_stimate": 0,
            }
        ],
    }
    stale = json.loads(json.dumps(canonical))
    stale["findings"][0]["occorrenze"][0]["nota"] = "riscritta dal cron"
    remote_file = tmp_path / "remote.json"
    source_file = tmp_path / "source.json"
    _write(remote_file, json.dumps(canonical))
    _write(source_file, json.dumps(stale))

    result = subprocess.run(
        ["python3", str(MERGER), str(remote_file), str(source_file), str(remote_file)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "modifica dati gia' presenti su main" in result.stderr
    assert json.loads(remote_file.read_text()) == canonical


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


def test_a_stale_local_jsonl_cannot_truncate_main(repo):
    """Una copia su disco piu' vecchia di main non deve troncare il ledger."""
    project, remote = repo["project"], repo["remote"]
    _dirty_the_ledger(project)
    _run_helper(repo, LEDGER, JSONL, REPORT)
    before = _remote_file(remote, JSONL)

    # regressione simulata: il file su disco perde una riga
    _write(project / JSONL, '{"data": "2026-08-25"}\n')

    result = _run_helper(repo, JSONL)

    # niente da aggiungere: le righe di main restano, il cron non si incastra
    assert result.returncode == 0, result.stdout + result.stderr
    assert _status_line(result.stdout) == "GIT_STATUS=nothing_to_commit"
    assert _remote_file(remote, JSONL) == before


def test_jsonl_day_published_on_main_survives_a_stale_local_copy(repo):
    """Il giorno pubblicato su main e quello nuovo del cron devono coesistere."""
    project, remote, tmp = repo["project"], repo["remote"], repo["tmp"]

    # main acquisisce un giorno che la copia sulla feature branch non ha
    side = tmp / "side-jsonl"
    subprocess.run(["git", "clone", str(remote), str(side)], check=True, capture_output=True)
    _git(side, "config", "user.email", "altro@alembic.test")
    _git(side, "config", "user.name", "Altro Agente")
    with (side / JSONL).open("a") as handle:
        handle.write('{"data": "2026-08-24", "spy": 0.01}\n')
    _git(side, "add", JSONL)
    _git(side, "commit", "-m", "giorno concorrente")
    _git(side, "push", "origin", "main")

    # la sessione appende il proprio giorno alla copia (vecchia) su disco
    with (project / JSONL).open("a") as handle:
        handle.write('{"data": "2026-08-26"}\n')

    result = _run_helper(repo, JSONL)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _status_line(result.stdout) == "GIT_STATUS=pushed"
    days = [
        json.loads(line)["data"]
        for line in _remote_file(remote, JSONL).splitlines()
        if line.strip()
    ]
    assert days == ["2026-08-25", "2026-08-24", "2026-08-26"]


def test_jsonl_conflicting_day_is_refused(tmp_path):
    """Stesso giorno con numeri diversi non e' una riga nuova: decide un umano."""
    remote_file = tmp_path / "remote.jsonl"
    source_file = tmp_path / "source.jsonl"
    canonical = '{"data": "2026-08-26", "spy": 0.01}\n'
    _write(remote_file, canonical)
    _write(source_file, '{"data": "2026-08-26", "spy": 0.99}\n')

    result = subprocess.run(
        ["python3", str(JSONL_MERGER), str(remote_file), str(source_file), str(remote_file)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "2026-08-26" in result.stderr
    assert remote_file.read_text() == canonical


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
        'cp docs/evidence/findings.json "$LEDGER_SNAPSHOT"\n'
        'cp docs/evidence/market_daily.jsonl "$JSONL_SNAPSHOT"\n'
        "printf '%s\\n' '{\"schema_version\":1,\"prossimo_id\":2,\"findings\":[{\"id\":\"F-001\",\"titolo\":\"Finding di test\",\"occorrenze\":[{\"data\":\"2026-08-26\",\"costo_usd\":1.0,\"nota\":\"test\",\"fonte\":\"REPORT_TEST.md\"}],\"costo_cumulato_usd\":1.0,\"occorrenze_non_stimate\":0}]}' > docs/evidence/findings.json\n"
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
            "LEDGER_SNAPSHOT": str(tmp / "ledger_visto_dalla_sessione.json"),
            "JSONL_SNAPSHOT": str(tmp / "market_daily_visto_dalla_sessione.jsonl"),
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
    result, log, telegram = _run_cron(repo)

    assert result.returncode == 0, log[-2000:]
    assert log.strip().splitlines()[-1] == "GIT_STATUS=pushed"
    assert _remote_file(repo["remote"], REPORT) == "# Alpha miss 2026-08-26\n"
    assert "F-001" in _remote_file(repo["remote"], LEDGER)
    assert "2026-08-26" in _remote_file(repo["remote"], ECON)
    assert "2026-08-26" in _remote_file(repo["remote"], "docs/evidence/dossier/2026-08-26.json")
    assert "GIT_STATUS=pushed" in telegram


def test_cron_alerts_when_the_ledger_does_not_reach_main(repo):
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


# --- riallineamento dei ledger prima della sessione (#336) -----------------


def _publish_on_main(repo: dict, finding_id: str, day: str) -> None:
    """Pubblica su main un finding e un giorno che la tree condivisa non ha."""
    side = repo["tmp"] / f"side-{finding_id}"
    subprocess.run(
        ["git", "clone", str(repo["remote"]), str(side)], check=True, capture_output=True
    )
    _git(side, "config", "user.email", "altro@alembic.test")
    _git(side, "config", "user.name", "Altro Agente")
    _write(
        side / LEDGER,
        json.dumps(
            {
                "schema_version": 1,
                "prossimo_id": 3,
                "findings": [
                    {
                        "id": finding_id,
                        "titolo": "Finding pubblicato da un altro autore",
                        "occorrenze": [
                            {
                                "data": day,
                                "costo_usd": 5.0,
                                "nota": "arrivato su main dopo il checkout",
                                "fonte": "REPORT_ALTRO.md",
                            }
                        ],
                        "costo_cumulato_usd": 5.0,
                        "occorrenze_non_stimate": 0,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
    )
    with (side / JSONL).open("a") as handle:
        handle.write(json.dumps({"data": day, "spy": 0.01}) + "\n")
    _git(side, "add", "-A")
    _git(side, "commit", "-m", f"evidence: {finding_id}")
    _git(side, "push", "origin", "main")


def test_cron_realigns_the_ledger_to_main_before_the_session_reads_it(repo):
    """La tree condivisa e' indietro: dossier e sessione devono vedere main."""
    _publish_on_main(repo, "F-002", "2026-08-24")

    result, log, _ = _run_cron(repo)

    assert result.returncode == 0, log[-2000:]
    seen = json.loads((repo["tmp"] / "ledger_visto_dalla_sessione.json").read_text())
    assert [finding["id"] for finding in seen["findings"]] == ["F-002"]
    assert seen["prossimo_id"] == 3
    days = [
        json.loads(line)["data"]
        for line in (repo["tmp"] / "market_daily_visto_dalla_sessione.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]
    assert days == ["2026-08-25", "2026-08-24"]


def test_refresh_never_discards_local_work_not_yet_on_main(repo):
    """Il riallineamento e' un'unione: cio' che non e' ancora su main resta."""
    project = repo["project"]
    _dirty_the_ledger(project)
    _publish_on_main(repo, "F-002", "2026-08-24")

    result = subprocess.run(
        ["bash", str(project / "scripts" / REFRESHER.name), LEDGER, JSONL],
        cwd=project,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ids = [finding["id"] for finding in json.loads((project / LEDGER).read_text())["findings"]]
    assert ids == ["F-002", "F-001"]
    days = [
        json.loads(line)["data"]
        for line in (project / JSONL).read_text().splitlines()
        if line.strip()
    ]
    assert days == ["2026-08-25", "2026-08-24", "2026-08-26"]


def test_refresh_leaves_the_local_ledger_alone_when_it_cannot_merge(repo):
    """Fail-open: un conflitto non deve far saltare l'analisi del giorno."""
    project = repo["project"]
    _publish_on_main(repo, "F-002", "2026-08-24")
    # stesso id, titolo diverso: il riallineamento non puo' decidere
    conflicting = json.dumps(
        {
            "schema_version": 1,
            "prossimo_id": 3,
            "findings": [
                {
                    "id": "F-002",
                    "titolo": "Titolo incompatibile",
                    "occorrenze": [],
                    "costo_cumulato_usd": 0.0,
                    "occorrenze_non_stimate": 0,
                }
            ],
        },
        indent=2,
    ) + "\n"
    _write(project / LEDGER, conflicting)

    result = subprocess.run(
        ["bash", str(project / "scripts" / REFRESHER.name), LEDGER],
        cwd=project,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ATTENZIONE" in result.stdout
    assert (project / LEDGER).read_text() == conflicting
