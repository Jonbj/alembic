"""Il cron alpha-miss e il forense DEVONO chiamare l'idempotency guard.

#564 / F-075 — senza la chiamata a `scripts/_alpha_miss_idempotency_guard.sh`
subito dopo la risoluzione di DATE_TARGET, un holiday weekday (Labor Day,
Memorial Day, Juneteenth, July 4 sui venerdi', ...) produce un run duplicato:
sessione Claude Code, dossier rigenerato, ledger ri-committato con messaggio
identico al run precedente.

Il test non lancia il cron end-to-end (il main flow chiama `claude` e
`uv run python3` con credenziali Alpaca — fuori dalla portata del test
unitario). Si limita a verifiche strutturali sul sorgente: la guard deve
essere invocata nel punto giusto, con i flag giusti, e la sua exit 0 deve
portare a `exit 0` del cron (un no-op corretto, non un fallimento).
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ALPHA_MISS = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"
FORENSIC = ROOT / "scripts" / "daily_analysis.sh"


def test_cron_alpha_miss_invoke_la_guard_subito_dopo_date_target() -> None:
    """`daily_alpha_miss_analysis.sh` deve chiamare l'idempotency guard con
    --ledger su market_daily.jsonl PRIMA del refresh del ledger (#510) e del
    fetch di origin/main (#507). Se la guard manca o e' messa dopo questi
    passi, il side-effect si e' gia' prodotto e la guard arriva troppo
    tardi — esattamente il bug della issue.
    """
    source = ALPHA_MISS.read_text()

    assert "_alpha_miss_idempotency_guard.sh" in source
    assert "--ledger" in source
    assert "docs/evidence/market_daily.jsonl" in source

    guard_idx = source.index("_alpha_miss_idempotency_guard.sh")
    refresh_idx = source.index("refresh_evidence_ledger.sh")
    fetch_idx = source.index("git fetch --quiet origin main")
    dossier_idx = source.index("alpha_miner_dossier.py")
    assert guard_idx < refresh_idx, (
        "idempotency guard deve stare prima del refresh del ledger, "
        "altrimenti il side-effect (riallineamento a main) e' gia' avvenuto"
    )
    assert guard_idx < fetch_idx, (
        "idempotency guard deve stare prima del fetch origin/main, "
        "altrimenti la rete e' gia' stata toccata"
    )
    assert guard_idx < dossier_idx, (
        "idempotency guard deve stare prima della generazione del dossier, "
        "altrimenti il dossier e' gia' stato riscritto"
    )


def test_cron_alpha_miss_esce_zero_su_guard_azzeccata() -> None:
    """Quando la guard riconosce DATE_TARGET come gia' processato, il cron
    deve fare `exit 0` pulito. Un exit != 0 paginerebbe Telegram e attiverebbe
    l'allerta, ma e' un no-op corretto, non un fallimento.
    """
    source = ALPHA_MISS.read_text()

    guard_idx = source.index("_alpha_miss_idempotency_guard.sh")
    tail = source[guard_idx:]
    # Il pattern case deve avere il ramo `0)` con `exit 0`
    assert "GUARD_STATUS" in tail
    assert "exit 0" in tail
    # Non deve essere un fallimento: il primo exit nel tail deve essere 0
    first_exit = tail.index("exit ")
    assert "exit 0" in tail[first_exit : first_exit + 30], (
        "l'uscita immediata del cron dopo la guard deve essere `exit 0`"
    )


def test_cron_forense_invoke_la_guard_con_report_e_commit_pattern() -> None:
    """`daily_analysis.sh` non scrive su market_daily.jsonl, quindi la sua
    guard deve usare la coppia (--report, --commit-pattern) — il check si
    attiva solo se ENTRAMBI sono presenti, e questo e' il punto che #564
    descrive al punto 2 della sezione 'Proposed fix'.
    """
    source = FORENSIC.read_text()

    assert "_alpha_miss_idempotency_guard.sh" in source
    assert "--report" in source
    assert "--commit-pattern" in source
    assert "--project-dir" in source
    assert "FORENSIC_DAILY_REPORT_${DATE_TARGET}.md" in source
    assert 'evidence: forensic ${DATE_TARGET}' in source

    guard_idx = source.index("_alpha_miss_idempotency_guard.sh")
    refresh_idx = source.index("refresh_evidence_ledger.sh")
    assert guard_idx < refresh_idx, (
        "idempotency guard forense deve stare prima del refresh del ledger"
    )


def test_cron_forense_esce_zero_su_guard_azzeccata() -> None:
    source = FORENSIC.read_text()

    guard_idx = source.index("_alpha_miss_idempotency_guard.sh")
    tail = source[guard_idx:]
    assert "GUARD_STATUS" in tail
    first_exit = tail.index("exit ")
    assert "exit 0" in tail[first_exit : first_exit + 30]
