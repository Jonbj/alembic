"""Regression #396: _s4_entry_intents qualifica decision_at e main() fallisce ad alta voce.

Il join con ``s4_intent_events`` (PR #354) espone ``decision_at`` su entrambi i
lati, rendendo ambiguo ogni reference non qualificato in WHERE/ORDER BY: la
query falliva con un parse error deterministico, ma l'eccezione veniva degenerata
a un ``INFO ... saltato`` e lo script usciva 0 — il cron non vedeva il fallimento.
"""

from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier


def test_s4_entry_intents_qualifica_decision_at_contro_ambiguita():
    """Entrambi i lati del join espongono decision_at: ogni reference deve
    essere qualificata con ``intent.``, altrimenti Postgres la rifiuta come
    ambigua (#396). E' un parse error, quindi basta ispezionare la query."""
    with patch.object(dossier, "_psql", return_value=[]) as psql:
        dossier._s4_entry_intents(dossier.date(2026, 8, 25))

    query = psql.call_args.args[0]
    assert "WHERE intent.decision_at" in query
    assert "ORDER BY intent.decision_at" in query
    # Nessun reference non qualificato nei due punti ambigui.
    assert "WHERE decision_at" not in query
    assert "ORDER BY decision_at" not in query


def test_main_esce_nonzero_se_una_query_fallisce():
    """Un giorno saltato per errore di query non puo' uscire 0 (#396): e' il
    caso che ha lasciato morire il dossier per 3 sedute senza che nessuno se
    ne accorgesse."""
    def boom(*args, **kwargs):
        raise SystemExit("Query fallita: column reference \"decision_at\" is ambiguous")

    with (
        patch.object(dossier, "_watchlist", return_value=["AAA"]),
        patch.object(dossier, "costruisci_dossier", side_effect=boom),
        patch.object(dossier, "scrivi"),
    ):
        rc = dossier.main(["2026-08-25"])

    assert rc == 1


def test_main_esce_zero_se_il_giorno_non_e_di_borsa():
    """Un giorno saltato perche' non e' una seduta di borsa resta uno skip
    benigno: distinto dal fallimento di query, non fa uscire non-zero."""
    def non_borsa(*args, **kwargs):
        raise dossier.GiornoNonBorsa(
            "2026-08-23: nessuna barra per l'intera watchlist — non e' un giorno di borsa."
        )

    with (
        patch.object(dossier, "_watchlist", return_value=["AAA"]),
        patch.object(dossier, "costruisci_dossier", side_effect=non_borsa),
        patch.object(dossier, "scrivi"),
    ):
        rc = dossier.main(["2026-08-23"])

    assert rc == 0