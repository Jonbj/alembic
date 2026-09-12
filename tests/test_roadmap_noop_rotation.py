"""Regression test per #569 — i no-op ripetuti non fermano la coda."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "roadmap_agent_loop.sh"


def _scrivi_eseguibile(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


def _dry_run(
    tmp_path: Path,
    impronta_salvata: str,
    versione_salvata: str = "2026-09-12T12:00:00Z",
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _scrivi_eseguibile(bin_dir / "codex", "exit 0\n")
    _scrivi_eseguibile(bin_dir / "git", "exit 0\n")
    _scrivi_eseguibile(
        bin_dir / "sha256sum",
        "cat >/dev/null\nprintf 'immutata  -\\n'\n",
    )
    _scrivi_eseguibile(
        bin_dir / "gh",
        """\
if [[ "$1 $2" == "pr list" ]]; then
    exit 0
fi
if [[ "$1 $2" == "issue view" ]]; then
    if [[ "$*" == *"--json state,labels"* ]]; then
        printf 'OPEN freeze-ok\\n'
    elif [[ "$*" == *"--json body,labels"* ]]; then
        printf '{"body":"invariato","labels":[{"name":"freeze-ok"}]}\\n'
    elif [[ "$*" == *"--json updatedAt"* ]]; then
        printf '2026-09-12T12:00:00Z\\n'
    elif [[ "$*" == *"--json title"* ]]; then
        printf 'Issue %s\\n' "$3"
    fi
    exit 0
fi
if [[ "$1" == "api" ]]; then
    printf '[]\\n'
    exit 0
fi
exit 1
""",
    )

    queue = tmp_path / "queue.txt"
    queue.write_text("10 prima\n11 seconda\n")
    noop_state = tmp_path / "noop.tsv"
    noop_state.write_text(
        f"10\t2\t{impronta_salvata}\t{versione_salvata}\t2026-09-12T12:00:01Z\n"
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ROADMAP_FORCE_ENGINE": "codex",
            "ROADMAP_QUEUE_FILE": str(queue),
            "ROADMAP_LOG_DIR": str(tmp_path / "logs"),
            "ROADMAP_NOOP_STATE_FILE": str(noop_state),
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=60,
        check=False,
    )


def test_due_noop_consecutivi_fanno_selezionare_la_issue_successiva(tmp_path: Path) -> None:
    result = _dry_run(tmp_path, impronta_salvata="immutata")

    assert result.returncode == 0, result.stderr
    assert "#10 — 2 no-op consecutivi, fuori rotazione" in result.stdout
    assert "Issue selezionata: #11" in result.stdout


def test_impronta_cambiata_riammette_la_issue_e_azzera_lo_stato(tmp_path: Path) -> None:
    result = _dry_run(tmp_path, impronta_salvata="precedente")

    assert result.returncode == 0, result.stderr
    assert "#10 — issue cambiata dopo l'ultimo no-op: rientra in rotazione" in result.stdout
    assert "Issue selezionata: #10" in result.stdout
    assert (tmp_path / "noop.tsv").read_text() == ""


def test_updated_at_successivo_riammette_la_issue_anche_con_impronta_uguale(
    tmp_path: Path,
) -> None:
    result = _dry_run(
        tmp_path,
        impronta_salvata="immutata",
        versione_salvata="2026-09-12T11:59:00Z",
    )

    assert result.returncode == 0, result.stderr
    assert "#10 — issue cambiata dopo l'ultimo no-op: rientra in rotazione" in result.stdout
    assert "Issue selezionata: #10" in result.stdout
    assert (tmp_path / "noop.tsv").read_text() == ""


def test_secondo_noop_ha_evento_e_notifica_distinti_senza_addebitare_fallimenti(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _scrivi_eseguibile(bin_dir / "codex", "printf 'Analisi conclusa.\\nNESSUNA PR\\n'\n")
    _scrivi_eseguibile(
        bin_dir / "git",
        """\
if [[ "$1 $2" == "worktree add" ]]; then
    mkdir -p "$5"
elif [[ "$1 $2" == "worktree remove" ]]; then
    rm -rf "$4"
fi
exit 0
""",
    )
    _scrivi_eseguibile(
        bin_dir / "curl",
        "printf '%s\\n' \"$*\" >> \"$TG_CAPTURE\"\n",
    )
    _scrivi_eseguibile(
        bin_dir / "gh",
        """\
if [[ "$1 $2" == "pr list" ]]; then
    exit 0
fi
if [[ "$1 $2" == "issue view" ]]; then
    if [[ "$*" == *"--json state,labels"* ]]; then
        printf 'OPEN freeze-ok\\n'
    elif [[ "$*" == *"--json body,labels"* ]]; then
        printf 'metadati-stabili\\n'
    elif [[ "$*" == *"--json comments"* ]]; then
        printf '2099-01-01T00:00:00Z\\n'
    elif [[ "$*" == *"--json updatedAt"* ]]; then
        printf '2099-01-01T00:00:00Z\\n'
    elif [[ "$*" == *"--json title"* ]]; then
        printf 'Issue %s\\n' "$3"
    fi
    exit 0
fi
if [[ "$1" == "api" ]]; then
    exit 0
fi
exit 1
""",
    )

    queue = tmp_path / "queue.txt"
    queue.write_text("10 prima\n")
    log_dir = tmp_path / "logs"
    telegram = tmp_path / "telegram.txt"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ROADMAP_FORCE_ENGINE": "codex",
            "ROADMAP_QUEUE_FILE": str(queue),
            "ROADMAP_LOG_DIR": str(log_dir),
            "TELEGRAM_BOT_TOKEN": "finto",
            "TELEGRAM_CHAT_ID": "finta",
            "TG_CAPTURE": str(telegram),
        }
    )

    for _ in range(2):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    eventi = [json.loads(line) for line in (log_dir / "roadmap_results.jsonl").read_text().splitlines()]
    assert [evento["result"] for evento in eventi] == ["noop", "noop_suspended"]
    assert eventi[-1]["noop_count"] == 2
    assert (log_dir / "roadmap_agent_state.tsv").read_text() == ""
    assert (log_dir / "roadmap_agent_noop_state.tsv").read_text().split("\t")[:2] == ["10", "2"]
    notifica = telegram.read_text()
    assert "no-op dichiarato" in notifica
    assert "fuori rotazione per no-op ripetuti" in notifica
    assert "retriage dell'operatore" in notifica
