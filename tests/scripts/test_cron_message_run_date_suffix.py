"""#565 / F-076: il messaggio di commit del cron include la data del run
(accanto alla data target), cosi' due commit sulla stessa DATE_TARGET —
un rewrite legittimo o un duplicato sfuggito alla guard — non sono
indistinguibili in ``git log``. La convenzione esplicita e' dichiarata
nella issue, voce 5 della sezione "Proposed fix".
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALPHA_MISS = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"
FORENSIC = ROOT / "scripts" / "daily_analysis.sh"


def test_cron_alpha_miss_commit_message_incluye_run_date():
    """Il cron alpha-miss committa con un messaggio unico per ogni run."""
    source = ALPHA_MISS.read_text()
    # la data del run e' la variabile $DATE che il cron calcola all'inizio
    # (``DATE=$(date +%Y-%m-%d)``); la DATE_TARGET e' l'ultima seduta di borsa
    # chiusa. Il messaggio deve citarle entrambe.
    assert '"evidence: ledger ${DATE_TARGET} (run ${DATE})"' in source, (
        "messaggio senza suffisso (run ${DATE}): un re-run sulla stessa "
        "DATE_TARGET sarebbe invisibile in `git log` (#565 / F-076, voce 5)"
    )


def test_cron_forense_commit_message_incluye_run_date():
    """Il cron forense committa con un messaggio unico per ogni run."""
    source = FORENSIC.read_text()
    assert '"evidence: forensic ${DATE_TARGET} (run ${DATE})"' in source, (
        "stesso problema del cron alpha-miss: due run sullo stesso giorno "
        "con messaggio identico sarebbero indistinguibili in `git log`"
    )
