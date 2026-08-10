"""Regression tests per #221 — riconoscimento della PR prodotta da un giro.

Il loop crea `agent/issue-<N>` ma gli agenti, quando rifanno il lavoro, pubblicano su
un branch derivato (`-v2`, `-v3`). Con la corrispondenza esatta sul nome del branch la
PR risultava inesistente: tentativo contato come fallimento, e soprattutto cancello di
review mai raggiunto. Materiale preso dai casi reali PR #220 (#191) e #217 (#185).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "roadmap_agent_loop.sh"


def _issue_del_branch(branch: str) -> str:
    res = subprocess.run(
        ["bash", str(SCRIPT), "--issue-del-branch", branch],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


def _trova_pr(issue: str, pr_list: list[dict], tmp_path: Path) -> str:
    """Esegue la ricerca della PR con un `gh` finto che restituisce `pr_list`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    payload = json.dumps(pr_list)
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env bash\ncat <<'PRJSON'\n" + payload + "\nPRJSON\n")
    gh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    res = subprocess.run(
        ["bash", str(SCRIPT), "--trova-pr", issue],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=60,
    )
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


class TestNumeroIssueDalBranch:
    """`--rivedi` ricavava la issue dalla CODA del nome: `-v3` diventava la issue #3."""

    @pytest.mark.parametrize(
        "branch,atteso",
        [
            ("agent/issue-191", "191"),
            ("agent/issue-191-v3", "191"),
            ("agent/issue-185-v2", "185"),
            ("agent/issue-208", "208"),
            ("agent/issue-134-v10", "134"),
        ],
    )
    def test_estrae_la_issue_dal_segmento_non_dalla_coda(self, branch: str, atteso: str) -> None:
        assert _issue_del_branch(branch) == atteso

    def test_branch_senza_issue_non_inventa_un_numero(self) -> None:
        assert _issue_del_branch("fix/211-verdict-parsing") == ""
        assert _issue_del_branch("main") == ""


class TestRiconoscimentoDellaPR:
    """La PR del giro va trovata anche se il branch non ha il nome atteso."""

    def test_branch_esatto(self, tmp_path: Path) -> None:
        prs = [{"number": 205, "headRefName": "agent/issue-191", "closingIssuesReferences": [{"number": 191}]}]
        assert _trova_pr("191", prs, tmp_path) == "205"

    def test_branch_derivato_v3_il_caso_reale_di_pr_220(self, tmp_path: Path) -> None:
        """PR #220 su `agent/issue-191-v3`: il loop la dichiarava inesistente."""
        prs = [{"number": 220, "headRefName": "agent/issue-191-v3", "closingIssuesReferences": [{"number": 191}]}]
        assert _trova_pr("191", prs, tmp_path) == "220"

    def test_branch_derivato_senza_closes_riconosciuto_dal_nome(self, tmp_path: Path) -> None:
        """Se la PR dice `Part of #N` invece di `closes`, resta il nome del branch."""
        prs = [{"number": 217, "headRefName": "agent/issue-185-v2", "closingIssuesReferences": []}]
        assert _trova_pr("185", prs, tmp_path) == "217"

    def test_closes_riconosciuto_anche_con_branch_arbitrario(self, tmp_path: Path) -> None:
        prs = [{"number": 300, "headRefName": "fix/qualcosa", "closingIssuesReferences": [{"number": 191}]}]
        assert _trova_pr("191", prs, tmp_path) == "300"

    def test_non_confonde_issue_con_prefisso_comune(self, tmp_path: Path) -> None:
        """`agent/issue-19` non deve rispondere per la issue #191, ne' viceversa."""
        prs = [{"number": 400, "headRefName": "agent/issue-19", "closingIssuesReferences": []}]
        assert _trova_pr("191", prs, tmp_path) == ""

    def test_nessuna_pr(self, tmp_path: Path) -> None:
        assert _trova_pr("191", [], tmp_path) == ""

    def test_pr_di_un_altra_issue_non_viene_scambiata(self, tmp_path: Path) -> None:
        prs = [{"number": 219, "headRefName": "agent/issue-134", "closingIssuesReferences": [{"number": 134}]}]
        assert _trova_pr("191", prs, tmp_path) == ""
