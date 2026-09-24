"""Regressione review #596: la misura deve applicare il filtro pre-registrato.

La pre-registrazione fissa la popolazione a:
- `execution_decisions.decision = 'SELL'` AND tick_time in finestra
- `exit_mechanism = 'below_entry_gate'` (weight-0 S4 in `_run_cycle_inner`)
- OPPURE `exit_mechanism IS NULL` AND `reason LIKE 'sentiment_reversal:%'`
  (le reversal non scrivono `exit_mechanism`: vivono in `reason`).

La misura precedente filtrava solo `decision='SELL' AND signal_id IS NOT NULL`,
contaminando il verdetto con uscite `target_hit`, `stop_loss`, ecc. — fuori
popolazione.

Questi test sono la guardia: anche se domani il WHERE della query si rompe o
qualcuno aggiunge un nuovo `exit_mechanism`, la popolazione resta ancorata al
criterio pre-registrato.
"""
from __future__ import annotations

from scripts.measure_596_exit_fanout_attribution import filter_population


def _row(
    decision: str = "SELL",
    exit_mechanism: str | None = None,
    reason: str | None = None,
    signal_id: int | None = 3861,
) -> dict:
    return {
        "decision": decision,
        "exit_mechanism": exit_mechanism,
        "reason": reason,
        "signal_id": signal_id,
    }


def test_below_entry_gate_row_is_in_population():
    """Una SELL con exit_mechanism='below_entry_gate' passa."""
    row = _row(exit_mechanism="below_entry_gate", reason="Portfolio rebalance: weight 0%.")
    assert filter_population([row]) == [row]


def test_sentiment_reversal_reason_is_in_population():
    """Una SELL senza exit_mechanism ma con reason 'sentiment_reversal: ...' passa."""
    row = _row(
        exit_mechanism=None,
        reason="sentiment_reversal: score -0.405 < threshold -0.30",
    )
    assert filter_population([row]) == [row]


def test_target_hit_is_out_of_population():
    """Una SELL target_hit NON e' below_entry_gate ne' reversal — fuori."""
    row = _row(exit_mechanism="target_hit", reason="price >= target")
    assert filter_population([row]) == []


def test_stop_loss_is_out_of_population():
    """Una SELL stop_loss NON e' below_entry_gate ne' reversal — fuori."""
    row = _row(exit_mechanism="stop_loss", reason="stop triggered")
    assert filter_population([row]) == []


def test_weight_drop_exits_are_out_of_population():
    """Le uscite S4 weight-drop (es. _reason_and_mechanism_for_non_s4_weight_drop)
    producono ``exit_mechanism = '<strategy>_weight_drop'`` — fuori popolazione
    per la misura #596 (la issue parla solo di below_entry_gate + reversal)."""
    row = _row(exit_mechanism="s4_weight_drop", reason="weight dropped to 0%")
    assert filter_population([row]) == []


def test_buy_rows_are_out_of_population():
    """Una BUY non e' una SELL — fuori per definizione."""
    row = _row(decision="BUY", exit_mechanism="below_entry_gate", reason="")
    assert filter_population([row]) == []


def test_reversal_without_prefix_is_out():
    """Una SELL NULL exit_mechanism ma con reason che non inizia per
    'sentiment_reversal:' NON e' reversal — fuori."""
    row = _row(exit_mechanism=None, reason="orphan decision, no live signal")
    assert filter_population([row]) == []


def test_reversal_substring_but_not_prefix_is_out():
    """Una reason che contiene 'sentiment_reversal' come substring ma NON come
    prefisso ('...':) NON entra: il pre-registrato usa LIKE 'sentiment_reversal:%'
    (anchored), non substring generico. Difensivo contro futuri testi di reason
    che citino la reversal senza esserlo."""
    row = _row(exit_mechanism=None, reason="note: prior sentiment_reversal here")
    assert filter_population([row]) == []


def test_population_mix_keeps_only_pre_registered_subset():
    """Una popolazione mista: solo below_entry_gate + reversal_reason passano."""
    rows = [
        _row(exit_mechanism="below_entry_gate", reason="Portfolio rebalance"),
        _row(exit_mechanism=None, reason="sentiment_reversal: score -0.40"),
        _row(exit_mechanism="target_hit", reason="hit target"),
        _row(exit_mechanism="stop_loss", reason="stop loss"),
        _row(exit_mechanism="s4_weight_drop", reason="weight 0"),
        _row(decision="BUY", exit_mechanism="below_entry_gate", reason="entry"),
    ]
    kept = filter_population(rows)
    assert len(kept) == 2
    assert kept[0]["exit_mechanism"] == "below_entry_gate"
    assert "sentiment_reversal" in (kept[1]["reason"] or "")