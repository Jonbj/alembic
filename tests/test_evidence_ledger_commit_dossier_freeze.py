"""#565 / F-076: il committer del ledger non sovrascrive in silenzio un
``docs/evidence/dossier/*.json`` gia' committato. Il difetto originale era
il ``cp`` fall-through documentato in #510 e lasciato aperto: la dest
gia' esiste su main, il file locale e' diverso, il ``cp`` copia, e il
commit successivo non rileva la sovrascrittura. Qui rifiutiamo la catena
intera con GIT_STATUS=not_committed, exit non-zero, e l'originale
committed intatto.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "commit_evidence_ledger.sh"
MERGER = ROOT / "scripts" / "merge_evidence_findings.py"
JSONL_MERGER = ROOT / "scripts" / "merge_evidence_jsonl.py"
REFRESHER = ROOT / "scripts" / "refresh_evidence_ledger.sh"
IDEMPOTENCY_GUARD = ROOT / "scripts" / "_alpha_miss_idempotency_guard.sh"
SCRIPTS = (HELPER, MERGER, JSONL_MERGER, REFRESHER, IDEMPOTENCY_GUARD)

DOSSIER_REL = "docs/evidence/dossier/2026-09-04.json"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return result.stdout


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


@pytest.fixture()
def repo_con_dossier_committato(tmp_path: Path) -> dict:
    """Repo con un dossier di una seduta chiusa gia' committato su main."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)],
        check=True, capture_output=True,
    )
    project = tmp_path / "project"
    subprocess.run(
        ["git", "clone", str(remote), str(project)], check=True, capture_output=True
    )
    _git(project, "config", "user.email", "cron@alembic.test")
    _git(project, "config", "user.name", "Cron Alembic")

    # ledger minimi per fare partire il setup
    _write(
        project / "docs/evidence/findings.json",
        json.dumps(
            {"schema_version": 1, "prossimo_id": 1, "findings": []}, indent=2
        ) + "\n",
    )
    _write(project / "docs/evidence/market_daily.jsonl", '{"data": "2026-08-25"}\n')

    # dossier committato: la "versione buona" che NON deve essere sovrascritta
    dossier_originale = {
        "data": "2026-09-04",
        "schema_version": "3.1",
        "prezzi_originali": {"WDC": 0.05863170052313338},
    }
    _write(
        project / DOSSIER_REL,
        json.dumps(dossier_originale, indent=2, ensure_ascii=False) + "\n",
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "evidence: dossier 2026-09-04")
    _git(project, "push", "origin", "main")

    # tree principale parcheggiata su un branch altrui (stesso pattern di
    # test_evidence_ledger_commit.py)
    _git(project, "checkout", "-b", "agent/issue-999")

    (project / "scripts").mkdir(exist_ok=True)
    for script in SCRIPTS:
        shutil.copy2(script, project / "scripts" / script.name)

    return {"remote": remote, "project": project, "tmp": tmp_path}


def _run_helper(repo: dict, *paths: str) -> subprocess.CompletedProcess[str]:
    env = __import__("os").environ.copy()
    env.update(
        {
            "EVIDENCE_WORKTREE": str(repo["tmp"] / "wt-evidence"),
            "EVIDENCE_PENDING_FILE": str(repo["tmp"] / "pending.txt"),
            "HOME": str(repo["tmp"] / "home"),
        }
    )
    return subprocess.run(
        [
            "bash",
            str(repo["project"] / "scripts" / HELPER.name),
            "--message",
            "evidence: ledger 2026-09-04",
            *paths,
        ],
        cwd=repo["project"],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _status_line(output: str) -> str:
    lines = [ln for ln in output.splitlines() if ln.startswith("GIT_STATUS=")]
    assert lines, f"nessuna riga GIT_STATUS nell'output:\n{output}"
    return lines[-1]


def _remote_dossier(repo: dict) -> dict:
    raw = subprocess.run(
        ["git", "--git-dir", str(repo["remote"]),
         "show", f"main:{DOSSIER_REL}"],
        text=True, capture_output=True, check=True,
    ).stdout
    return json.loads(raw)


def test_dossier_diverso_da_committed_viene_rifiutato(repo_con_dossier_committato):
    """La catena abortisce con not_committed e l'originale resta su main."""
    project = repo_con_dossier_committato["project"]
    # la seduta corrente tenta di riscrivere il dossier con prezzi diversi
    dossier_nuovo = {
        "data": "2026-09-04",
        "schema_version": "3.1",
        "prezzi_originali": {"WDC": 0.058627641981741085},  # <- diverso
    }
    _write(
        project / DOSSIER_REL,
        json.dumps(dossier_nuovo, indent=2, ensure_ascii=False) + "\n",
    )

    result = _run_helper(repo_con_dossier_committato, DOSSIER_REL)
    assert result.returncode != 0, result.stdout + result.stderr
    assert _status_line(result.stdout) == "GIT_STATUS=not_committed"

    # l'originale su main NON e' stato toccato
    committed = _remote_dossier(repo_con_dossier_committato)
    assert committed["prezzi_originali"]["WDC"] == pytest.approx(
        0.05863170052313338, rel=1e-12
    )


def test_dossier_identico_al_committed_passa_in_silenzio(repo_con_dossier_committato):
    """Un commit che non cambia nulla (nothing_to_commit) deve comunque
    passare senza errori: la guard si attiva solo sulla differenza di
    contenuto, non sull'esistenza del path."""
    project = repo_con_dossier_committato["project"]
    # riscrivi byte-per-byte lo stesso file
    committed = _remote_dossier(repo_con_dossier_committato)
    _write(
        project / DOSSIER_REL,
        json.dumps(committed, indent=2, ensure_ascii=False) + "\n",
    )

    result = _run_helper(repo_con_dossier_committato, DOSSIER_REL)
    assert _status_line(result.stdout) == "GIT_STATUS=nothing_to_commit"


def test_regen_file_non_viene_rifiutato(repo_con_dossier_committato):
    """Un file ``.regen-<ts>.json`` non ha controparte committed: passa."""
    project = repo_con_dossier_committato["project"]
    regen_rel = "docs/evidence/dossier/2026-09-04.regen-20260908T120000.json"
    regen_payload = {
        "data": "2026-09-04",
        "schema_version": "3.1",
        "prezzi_originali": {"WDC": 0.058627641981741085},  # nuovo
    }
    _write(
        project / regen_rel,
        json.dumps(regen_payload, indent=2, ensure_ascii=False) + "\n",
    )

    result = _run_helper(repo_con_dossier_committato, regen_rel)
    assert _status_line(result.stdout) == "GIT_STATUS=pushed", (
        result.stdout + result.stderr
    )

    # Leggiamo dal remote bare: refs locali del project sono stale dopo push.
    raw = subprocess.run(
        ["git", "--git-dir", str(repo_con_dossier_committato["remote"]),
         "show", f"main:{regen_rel}"],
        text=True, capture_output=True, check=True,
    ).stdout
    assert json.loads(raw)["prezzi_originali"]["WDC"] == pytest.approx(
        0.058627641981741085, rel=1e-12
    )
