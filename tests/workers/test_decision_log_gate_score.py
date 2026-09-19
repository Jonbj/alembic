"""#550 (F-073) — le righe del Decision Log dichiarano il punteggio del gate.

DoD della issue: un test simula un boost che sposta un segnale attraverso il
gate e verifica che la riga persistita lo dichiari. SKIP_THRESHOLD e BUY
estraggono i campi dagli stessi helper, nutriti dalla provenienza del ranker
(score = decidente, raw_score/velocity_multiplier = scomposizione) o dal
re-fetch by-id (solo grezzo, moltiplicatore NULL).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from src.workers import portfolio_scheduler


# ---------------------------------------------------------------------------
# _s4_decision_score_fields — estrazione campi per la riga
# ---------------------------------------------------------------------------


def test_dalla_provenienza_boostata_la_riga_porta_grezzo_e_moltiplicatore():
    prov = {
        "signal_id": 11429,
        "score": 0.3285,        # decidente: quello che il gate ha confrontato
        "raw_score": 0.27375,   # il grezzo di sentiment_signals
        "velocity_multiplier": 1.2,
    }

    fields = portfolio_scheduler._s4_decision_score_fields(prov)

    assert fields["signal_score"] == 0.27375
    assert fields["velocity_multiplier"] == 1.2


def test_dalla_provenienza_senza_boost_il_moltiplicatore_e_unitario():
    """Il ranker defaulta velocity_multiplier a 1.0: la riga dichiara 1.0
    (strumentato, nessun boost), non NULL."""
    prov = {"signal_id": 7, "score": 0.42, "raw_score": 0.42, "velocity_multiplier": 1.0}

    fields = portfolio_scheduler._s4_decision_score_fields(prov)

    assert fields["signal_score"] == 0.42
    assert fields["velocity_multiplier"] == 1.0


def test_dal_refetch_by_id_solo_grezzo_moltiplicatore_null():
    """Provenienza persa (path difensivo): resta il grezzo del re-fetch, ma il
    moltiplicatore e' NULL — «non strumentato», mai 1.0 implicito."""
    fields = portfolio_scheduler._s4_decision_score_fields({"score": 0.42})

    assert fields["signal_score"] == 0.42
    assert fields["velocity_multiplier"] is None


def test_provenienza_assente_riga_non_s4():
    assert portfolio_scheduler._s4_decision_score_fields(None) == {
        "signal_score": None,
        "velocity_multiplier": None,
    }


# ---------------------------------------------------------------------------
# _s4_sentiment_reason_clause — la riga si spiega da sola nel reason
# ---------------------------------------------------------------------------


def test_la_clausola_dichiara_la_decomposizione_quando_c_e_boost():
    """Il grezzo lo stampa la frase «sentiment +0.274» del chiamante: la
    clausola aggiunge moltiplicatore e decidente, senza ridirlo."""
    clause = portfolio_scheduler._s4_sentiment_reason_clause(0.27375, 1.2)

    assert "1.20" in clause
    assert "0.328" in clause  # il decidente: 0.27375 × 1.2 = 0.3285 → .3f


def test_senza_boost_la_clausola_e_vuota():
    """Reason invariato per la massa delle righe non boostate."""
    assert portfolio_scheduler._s4_sentiment_reason_clause(0.42, 1.0) == ""
    assert portfolio_scheduler._s4_sentiment_reason_clause(0.42, None) == ""


# ---------------------------------------------------------------------------
# _record_gate_drops — SKIP_THRESHOLD con scomposizione
# ---------------------------------------------------------------------------


def test_skip_threshold_registra_grezzo_e_moltiplicatore_e_reason_vero():
    """Il caso della issue al contrario: il boost NON basta a passare il gate.
    La riga deve mostrare il confronto VERO (decidente < soglia), non il
    confronto fra grezzo e soglia, che sarebbe falso in generale."""
    dropped = pd.DataFrame([
        {
            "symbol": "AMAT",
            "score": 0.288,           # decidente (post-velocity)
            "raw_score": 0.240,       # grezzo
            "velocity_multiplier": 1.2,
            "signal_id": 123,
        },
    ])
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7):
        portfolio_scheduler._record_gate_drops(dropped, threshold=0.300)

    call = mock_pg.write_execution_decision.call_args
    assert call.kwargs["decision"] == "SKIP_THRESHOLD"
    assert call.kwargs["signal_score"] == 0.240       # il grezzo
    assert call.kwargs["velocity_multiplier"] == 1.2  # la spiegazione
    # il reason confronta il DECIDENTE con la soglia e mostra la scomposizione
    assert "0.288" in call.kwargs["reason"]
    assert "0.240" in call.kwargs["reason"]
    assert "1.20" in call.kwargs["reason"]
    assert "0.300" in call.kwargs["reason"]
