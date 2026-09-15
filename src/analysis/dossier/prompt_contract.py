"""Contratto versionato fra il prompt del cron alpha-miss e lo schema del
dossier (#287, P1).

Il prompt e' l'unico punto in cui il cron dice alla sessione Claude cosa fare;
finora non dichiarava una versione e nulla verificava che la sua idea di
dossier combaciasse con lo schema realmente generato. Una combinazione
incompatibile produce report e righe di ledger che nessuno puo' difendere,
quindi il contratto e' esplicito e la verifica e' fail-closed: il cron
rifiuta la seduta su dossier incompatibile invece di improvvisare.

Modulo puro: nessun I/O, solo costanti e una funzione su Mapping.
"""

from __future__ import annotations

from typing import Any, Mapping

# Versione del contratto operativo (PROMPT heredoc in
# scripts/daily_alpha_miss_analysis.sh): cambia quando cambia cio' che il
# prompt chiede alla sessione o la forma del file dei candidati. Il file dei
# candidati la dichiara e il materializzatore la verifica.
PROMPT_VERSION = "alpha_miss_prompt_v2"

# Versioni di DOSSIER_SCHEMA_VERSION (scripts/alpha_miner_dossier.py) con cui
# questo prompt sa lavorare. Se una PR fa salire lo schema del dossier senza
# toccare questa lista, il cron si ferma: e' il fallimento giusto.
SCHEMA_DOSSIER_COMPATIBILI = frozenset({"3.1"})


def verifica_compatibilita_schema(dossier: Mapping[str, Any]) -> dict[str, Any]:
    """Verifica che il dossier sia leggibile dal prompt PROMPT_VERSION.

    Ritorna ``{"ok", "errors", "prompt_version", "schema_version"}``.
    ``ok`` e' False per schema assente o sconosciuto: mai silenzioso.
    """
    schema = dossier.get("schema_version")
    errors: list[str] = []
    if not isinstance(schema, str) or not schema:
        errors.append(
            "dossier senza schema_version leggibile: il prompt "
            f"{PROMPT_VERSION} non puo' consumarlo"
        )
    elif schema not in SCHEMA_DOSSIER_COMPATIBILI:
        errors.append(
            f"schema dossier {schema} non compatibile col prompt {PROMPT_VERSION} "
            f"(compatibili: {', '.join(sorted(SCHEMA_DOSSIER_COMPATIBILI))})"
        )
    return {
        "ok": not errors,
        "errors": errors,
        "prompt_version": PROMPT_VERSION,
        "schema_version": schema if isinstance(schema, str) else None,
    }