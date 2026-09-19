"""Idempotency guard dei cron alpha-miss e forense (#564 / F-075).

I due cron giornalieri (`daily_alpha_miss_analysis.sh` e `daily_analysis.sh`)
risolvono `DATE_TARGET` come ultima seduta di borsa chiusa — il che, dopo un
holiday weekday, e' la stessa data gia' analizzata il giorno prima. Senza
guard, lanciano una sessione Claude Code intera, rigenerano il dossier e
riscrivono il report forense, riaprendo un commit `evidence: ledger YYYY-MM-DD`
sotto un messaggio identico al precedente. La guard qui testata e' un
mechanism check che restituisce exit 0 quando la data e' gia' a ledger, cosi'
i cron possono fare `exit 0` pulito invece di invocare `claude -p`.

Sono due i ledger da considerare:

* `docs/evidence/market_daily.jsonl` per l'alpha-miss — una riga per seduta,
  campo `data: "YYYY-MM-DD"`. E' la chiave piu' economica perche' e' gia'
  l'output osservazionale di questa pipeline.
* `docs/FORENSIC_DAILY_REPORT_${DATE_TARGET}.md` insieme al commit
  `evidence: forensic ${DATE_TARGET}` per il forense: il forense non scrive
  su `market_daily.jsonl`, quindi la sua chiave deve essere l'esistenza del
  report gia' committato, non un ledger parallelo.

Il check si limita a leggere lo stato e a uscire: nessuna scrittura, nessun
side-effect. Il caller decide cosa fare con exit 0 (tipicamente `exit 0`
diretto — l'uscita e' un no-op corretto, non un fallimento).
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "_alpha_miss_idempotency_guard.sh"


def _write_ledger(project: Path, target: str) -> Path:
    ledger = project / "docs" / "evidence" / "market_daily.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        '{"data": "2026-09-01", "spy": 0.0}\n'
        f'{{"data": "{target}", "spy": 0.0042}}\n'
        '{"data": "2026-09-05", "spy": -0.001}\n'
    )
    return ledger


def _run_helper(
    project: Path,
    target: str,
    *,
    ledger: Path | None,
    report: Path | None = None,
    commit_pattern: str | None = None,
    project_dir: Path | None = None,
    extra_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        str(HELPER),
        "--date-target",
        target,
        "--ledger",
        str(ledger) if ledger is not None else "/nonexistent/market_daily.jsonl",
    ]
    if report is not None:
        args += ["--report", str(report)]
    if commit_pattern is not None:
        args += ["--commit-pattern", commit_pattern]
    if project_dir is not None:
        args += ["--project-dir", str(project_dir)]
    env = os.environ.copy()
    env["PROJECT_DIR"] = str(project)
    if extra_path:
        env["PATH"] = f"{extra_path}:{env['PATH']}"
    return subprocess.run(args, env=env, text=True, capture_output=True, check=False)


def _fake_git(bin_dir: Path, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_git = bin_dir / "git"
    fake_git.write_text("#!/usr/bin/env bash\n" + body)
    fake_git.chmod(0o755)


def test_guard_esce_zero_quando_date_target_e_a_ledger(tmp_path: Path) -> None:
    """Caso #564: il 2026-09-07 (Labor Day) ha rieseguito il 2026-09-04 — la
    guard deve intercettare il caso e uscire 0 con un messaggio leggibile,
    PRIMA che il cron chiami `claude -p` e produca un nuovo dossier.
    """
    target = "2026-09-04"
    ledger = _write_ledger(tmp_path, target)

    result = _run_helper(tmp_path, target, ledger=ledger)

    assert result.returncode == 0, result.stderr
    assert "gia'" in result.stdout.lower() or "skip" in result.stdout.lower()
    assert target in result.stdout


def test_guard_esce_zero_quando_esiste_gia_il_report_forense_e_il_commit(
    tmp_path: Path,
) -> None:
    """Il forense non scrive su `market_daily.jsonl`: la sua guard usa la
    coppia (report esiste, commit con messaggio atteso su origin/main). Se
    entrambe sono presenti la data e' gia' stata processata e la guard esce
    0, cosi' `daily_analysis.sh` puo' fare `exit 0` pulito.

    Il commit va cercato su `origin/main`, non su HEAD: il commit forense lo
    fa `commit_evidence_ledger.sh` da una worktree dedicata appuntata su
    main, mentre la tree condivisa da cui gira il cron e' abitualmente
    parcheggiata sul branch di lavoro di un altro agente (#411) — su HEAD
    quel commit spesso non c'e', e la guard girerebbe a vuoto.
    """
    target = "2026-09-04"
    report = tmp_path / "docs" / f"FORENSIC_DAILY_REPORT_{target}.md"
    report.parent.mkdir(parents=True)
    report.write_text("# vecchio report\n")

    bin_dir = tmp_path / "bin"
    _fake_git(
        bin_dir,
        "if [[ \"$1\" == '-C' && \"$2\" == \"$PROJECT_DIR\" "
        "&& \"$3\" == 'log' && \"$4\" == '--oneline' && \"$5\" == 'origin/main' "
        "&& \" $* \" == *\" --grep=evidence: forensic \"* ]]; then\n"
        f"  printf 'a3fd8b1 evidence: forensic {target}\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exit 9\n",
    )

    result = _run_helper(
        tmp_path,
        target,
        ledger=None,
        report=report,
        commit_pattern=f"evidence: forensic {target}",
        project_dir=tmp_path,
        extra_path=str(bin_dir),
    )

    assert result.returncode == 0, result.stderr
    assert target in result.stdout


def test_guard_forense_ignora_un_commit_presente_solo_su_head(tmp_path: Path) -> None:
    """Regressione del caso produzione (#564): la tree condivisa e' parcheggiata
    su un branch di lavoro che contiene il commit forense (o un suo cherry-pick)
    ma main non lo ha — per esempio un run precedente il cui push e' fallito e
    che e' rimasto su una branch locale. Un `git log` su HEAD lo troverebbe e
    fermerebbe il cron per una seduta che invece NON e' mai arrivata su main.
    La guard deve guardare solo origin/main.
    """
    target = "2026-09-04"
    report = tmp_path / "docs" / f"FORENSIC_DAILY_REPORT_{target}.md"
    report.parent.mkdir(parents=True)
    report.write_text("# vecchio report\n")

    bin_dir = tmp_path / "bin"
    _fake_git(
        bin_dir,
        # risponde SOLO alla forma senza ref (HEAD): qualsiasi invocazione che
        # chieda origin/main non trova nulla
        "if [[ \"$1\" == 'log' && \"$2\" == '--oneline' "
        "&& \" $* \" != *' origin/main '* ]]; then\n"
        f"  printf 'a3fd8b1 evidence: forensic {target}\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
    )

    result = _run_helper(
        tmp_path,
        target,
        ledger=None,
        report=report,
        commit_pattern=f"evidence: forensic {target}",
        project_dir=tmp_path,
        extra_path=str(bin_dir),
    )

    assert result.returncode == 1, result.stderr


def test_guard_forense_senza_project_dir_non_interroga_git(tmp_path: Path) -> None:
    """Il cron gira dalla cwd della crontab, non dal repo (il `cd
    \"$PROJECT_DIR\"` arriva dopo): senza --project-dir la guard non puo'
    interrogare git in modo affidabile e deve trattare il check commit come
    non disponibile — procede (exit 1) invece di fermarsi su un'ipotesi.
    """
    target = "2026-09-04"
    report = tmp_path / "docs" / f"FORENSIC_DAILY_REPORT_{target}.md"
    report.parent.mkdir(parents=True)
    report.write_text("# vecchio report\n")

    bin_dir = tmp_path / "bin"
    # qualunque invocazione di git e' un fallimento del test: non deve avvenire
    _fake_git(bin_dir, "echo 'git non doveva essere invocato' >&2\nexit 9\n")

    result = _run_helper(
        tmp_path,
        target,
        ledger=None,
        report=report,
        commit_pattern=f"evidence: forensic {target}",
        project_dir=None,
        extra_path=str(bin_dir),
    )

    assert result.returncode == 1, result.stderr
    assert "git non doveva essere invocato" not in result.stderr


def test_guard_esce_uno_quando_date_target_non_e_a_ledger(tmp_path: Path) -> None:
    """Caso felice del cron: prima sessione su una nuova data, niente a
    ledger. La guard dice al caller di procedere (exit 1 e' il convenuto:
    il caller lo inverte per significare 'guard NON scattata').
    """
    target = "2026-09-08"
    ledger = _write_ledger(tmp_path, "2026-09-04")  # contiene altre date, non target

    result = _run_helper(tmp_path, target, ledger=ledger)

    assert result.returncode == 1, result.stderr
    assert "procedi" in result.stdout.lower() or target in result.stdout


def test_guard_non_invocata_continua_se_ledger_esiste_ma_data_non_e_presente(
    tmp_path: Path,
) -> None:
    """Il ledger puo' esistere ma non contenere la data target: la guard non
    deve scattare — solo una corrispondenza esatta nel campo `data` ferma il
    cron. Questo e' il caso del riavvio dopo deploy (ledger presente ma
    DATE_TARGET non ancora processato).
    """
    target = "2026-09-30"
    ledger = _write_ledger(tmp_path, "2026-09-04")

    result = _run_helper(tmp_path, target, ledger=ledger)

    assert result.returncode == 1, result.stderr


def test_guard_gestisce_ledger_assente_senza_crashing(tmp_path: Path) -> None:
    """Alla prima installazione il ledger non esiste ancora: la guard non
    deve abortire (exit != 0/1) per il solo fatto che il file manca. Deve
    semplicemente segnalare 'procedi' come se il ledger fosse vuoto.
    """
    target = "2026-09-04"

    result = _run_helper(tmp_path, target, ledger=None)

    assert result.returncode == 1, result.stderr


def test_guard_rigetta_il_run_duplicato_del_2026_09_04(tmp_path: Path) -> None:
    """Test di regressione specifico per #564 / F-075: il 2026-09-07 (Labor
    Day) ha rieseguito il 2026-09-04 (commits e5512c9 e 88bfb05, stesso
    messaggio). Con un `market_daily.jsonl` reale che contiene gia' la riga
    del 2026-09-04 — come accade dopo il run di quel giorno — la guard
    invocata con gli stessi argomenti del cron (`--date-target 2026-09-04
    --ledger <path>`) deve uscire 0 e NON scrivere nulla sul filesystem del
    test. Questo e' il comportamento che il cron alpha-miss ora assume.
    """
    target = "2026-09-04"
    ledger = _write_ledger(tmp_path, target)

    before = sorted(p.name for p in tmp_path.rglob("*"))

    result = _run_helper(tmp_path, target, ledger=ledger)

    after = sorted(p.name for p in tmp_path.rglob("*"))
    assert result.returncode == 0, result.stderr
    assert before == after, "la guard non deve produrre side-effect sul filesystem"


def test_guard_forense_non_scattata_se_solo_il_report_esiste_ma_manca_il_commit(
    tmp_path: Path,
) -> None:
    """Il report forense puo' esistere come file ma senza commit su main
    (per esempio dopo uno stash): la guard non deve fermarsi perche' uno
    solo dei due segnali e' presente, dato che il commit e' la prova che
    la seduta e' stata osservabilmente pubblicata.
    """
    target = "2026-09-04"
    report = tmp_path / "docs" / f"FORENSIC_DAILY_REPORT_{target}.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report non committato\n")

    bin_dir = tmp_path / "bin"
    _fake_git(
        bin_dir,
        "if [[ \"$1\" == '-C' && \"$3\" == 'log' && \"$5\" == 'origin/main' ]]; then\n"
        "  printf ''\n"
        "  exit 0\n"
        "fi\n"
        "exit 9\n",
    )

    result = _run_helper(
        tmp_path,
        target,
        ledger=None,
        report=report,
        commit_pattern=f"evidence: forensic {target}",
        project_dir=tmp_path,
        extra_path=str(bin_dir),
    )

    assert result.returncode == 1, result.stderr
