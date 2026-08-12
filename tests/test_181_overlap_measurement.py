"""#181: misura dell'overlap S1∩S4 sui target BUY per ciclo.

L'issue chiede di capire se l'overlay S4 conferma S1 o gli duplica il
book. Tre affinamenti specificati dall'issue che i test inchiodano:

  1. Jaccard degli insiemi di ticker con peso target > 0, per ciclo
     (non un singolo aggregato).
  2. Correlazione dei pesi target — due sleeve possono toccare gli
     stessi ticker con pesi molto diversi.
  3. Confronto con il baseline atteso da selezione casuale, viste le
     diverse dimensioni delle sleeve.
  4. Classificazione del disaccordo:
       - "S4 compra ciò che S1 ignora" (no S1 BUY nello stesso ciclo)
       - "S4 compra ciò che S1 vende" (S1 SELL sullo stesso ticker
         nello stesso ciclo o appena prima — reversal, vedi #182)

L'attribuzione S1/S4 non e' assunta: la verifica e' parte della DoD.
I BUY S1 hanno `reason LIKE 'S1%'`, i BUY S4 hanno `reason LIKE 'S4%'`
con `signal_id IS NOT NULL`. I pochi `S4+S1` (entrambi i tag in
`reason`) vanno contati in entrambe le sleeve.

La firma di "ciclo" deve essere in sensata fra le due sleeve:
S4 ribilancia ogni 15 minuti, S1 e' MONTHLY dopo #185. Quindi il
"ciclo di confronto" non puo' essere un intervallo di 15 minuti per
entrambi. La scelta, motivata nell'evidence doc, e' di usare la
grana temporale di S1 (l'evento piu' raro) e aggregare le BUY S4
nella finestra precedente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.measure_181_overlap import (
    classify_disagreement,
    compute_per_cycle_overlap,
    expected_jaccard_random_baseline,
    jaccard,
    split_by_sleeve,
    weight_correlation,
)


# ── helpers minimi, niente DB, niente datetime.now() ──────────────────────────


def _ts(year: int, month: int, day: int, hour: int = 17, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _s1_buy(symbol: str, weight: float, ts: datetime) -> dict:
    return {
        "tick_time": ts,
        "symbol": symbol,
        "decision": "BUY",
        "reason": f"S1 momentum: time-series momentum signal, portfolio weight {weight * 100:.1f}%.",
        "score": weight,
        "signal_id": None,
    }


def _s4_buy(symbol: str, weight: float, ts: datetime) -> dict:
    return {
        "tick_time": ts,
        "symbol": symbol,
        "decision": "BUY",
        "reason": f"S4 news-driven: sentiment +0.500 (ensemble:glm-5.2), portfolio weight {weight * 100:.1f}%.",
        "score": weight,
        "signal_id": 12345,  # un signal_id fittizio non nullo
    }


def _s4_s1_buy(symbol: str, weight: float, ts: datetime) -> dict:
    """Caso raro ma reale: righe tagged 'S4+S1' (entrambi i sleeve)."""
    return {
        "tick_time": ts,
        "symbol": symbol,
        "decision": "BUY",
        "reason": f"S4+S1 news-driven: sentiment +0.500 (ensemble), portfolio weight {weight * 100:.1f}%.",
        "score": weight,
        "signal_id": 12345,
    }


# ── 1. Jaccard insiemistica su un caso controllato ────────────────────────────


def test_jaccard_full_overlap_is_one():
    assert jaccard({"AAPL", "MSFT", "GOOG"}, {"AAPL", "MSFT", "GOOG"}) == pytest.approx(1.0)


def test_jaccard_disjoint_is_zero():
    assert jaccard({"AAPL", "MSFT"}, {"GOOG", "AMZN"}) == 0.0


def test_jaccard_partial_overlap_matches_formula():
    # |S1 ∩ S4| / |S1 ∪ S4| = 1 / 3
    assert jaccard({"AAPL", "MSFT"}, {"MSFT", "GOOG"}) == pytest.approx(1 / 3)


def test_jaccard_handles_empty_intersection():
    # Uno dei due insiemi vuoto: Jaccard definita come 0 (entrambi vuoti = 1).
    assert jaccard(set(), {"AAPL"}) == 0.0


def test_jaccard_both_empty_is_one():
    # Convenzione: sleeve entrambe senza target = perfettamente allineate
    # sul vuoto. Serve al denominatore del ciclo senza BUY.
    assert jaccard(set(), set()) == 1.0


# ── 2. Correlazione pesata — distinta dalla Jaccard ──────────────────────────


def test_weight_correlation_high_when_weights_track():
    # Stesso ticker, pesi entrambi con varianza: correlazione +1.
    s1 = {"AAPL": 0.012, "MSFT": 0.020}
    s4 = {"AAPL": 0.014, "MSFT": 0.024}
    # v1=(0.012, 0.020), v4=(0.014, 0.024) → entrambi con stessa direzione
    assert weight_correlation(s1, s4) == pytest.approx(1.0)


def test_weight_correlation_zero_when_one_sleeve_has_constant_weight():
    # S4 mette lo stesso peso su tutti i ticker: la deviazione standard
    # e' zero, e per convenzione (definizione di Pearson con sd=0)
    # ritorniamo 0.0. La domanda "i pesi si muovono insieme?" non e'
    # neppure posta quando una delle due sleeve non varia.
    s1 = {"AAPL": 0.012, "MSFT": 0.014}
    s4 = {"AAPL": 0.020, "MSFT": 0.020}
    assert weight_correlation(s1, s4) == 0.0


def test_weight_correlation_negative_on_disjoint():
    # Universo disgiunto: S1 mette peso dove S4 NON mette peso.
    # v1 = (0.012, 0.000), v4 = (0.000, 0.020) → correlazione -1.
    s1 = {"AAPL": 0.012}
    s4 = {"GOOG": 0.020}
    assert weight_correlation(s1, s4) == pytest.approx(-1.0)


def test_weight_correlation_inverted_means_overlap_with_opposite_size():
    # Stesso ticker, pesi relativi invertiti: la sleeve che compra di piu'
    # sull'unico ticker condiviso e' la piu' grande, non l'altra.
    s1 = {"AAPL": 0.020, "MSFT": 0.010}
    s4 = {"AAPL": 0.010, "MSFT": 0.020}
    # I pesi sono (0.02, 0.01) per S1 e (0.01, 0.02) per S4 → corr = -1
    assert weight_correlation(s1, s4) == pytest.approx(-1.0)


# ── 3. Baseline atteso da selezione casuale ──────────────────────────────────


def test_baseline_jaccard_with_equal_sleeves_and_full_universe():
    # Universo = 96 (config S1), entrambe le sleeve 10. La selezione
    # casuale produce un overlap atteso |S1|*|S4|/N = 100/96 = 1.04
    # ticker su un'unione attesa di ~19 → Jaccard ~0.055.
    baseline = expected_jaccard_random_baseline(n_universe=96, n_s1=10, n_s4=10)
    # Formula: (n_s1 * n_s4 / N) / (n_s1 + n_s4 - n_s1*n_s4/N)
    expected = (100 / 96) / (20 - 100 / 96)
    assert baseline == pytest.approx(expected)
    assert baseline < 0.2  # sanity: e' un overlap piccolo per costruzione


def test_baseline_jaccard_scales_with_sleeve_size():
    # Una sleeve piu' grande sposta il baseline verso l'alto.
    small = expected_jaccard_random_baseline(n_universe=96, n_s1=5, n_s4=5)
    big = expected_jaccard_random_baseline(n_universe=96, n_s1=20, n_s4=20)
    assert big > small


# ── 4. Ciclo di confronto: usa la grana di S1 (l'evento piu' raro) ───────────


def test_per_cycle_overlap_groups_s4_buys_into_preceding_s1_window():
    # Una decisione S1 il 2026-08-01 alle 14:00, una S4 nello stesso giorno.
    # La S4 cade *prima* della S1 (es. 13:30): la finestra precedente e'
    # [S1 precedente, S1 corrente] e la contiene.
    s1 = [_s1_buy("AAPL", 0.012, _ts(2026, 8, 1, 14, 0))]
    s4 = [_s4_buy("AAPL", 0.020, _ts(2026, 8, 1, 13, 30))]

    cycles = compute_per_cycle_overlap(
        s1_buys=s1,
        s4_buys=s4,
        cycle_window=timedelta(days=30),
    )

    assert len(cycles) == 1
    # Stesso ticker presente in entrambe le sleeve nello stesso ciclo.
    assert cycles[0]["n_s1"] == 1
    assert cycles[0]["n_s4"] == 1
    assert cycles[0]["jaccard"] == pytest.approx(1.0)
    # Con un solo ticker condiviso, la sd di S4 e' zero → correlazione
    # convenzionalmente 0.0. La Jaccard (=1) e' la misura informativa
    # in questo caso; la correlazione pesata diventa >0 solo con piu'
    # ticker sovrapposti (test sotto).
    assert cycles[0]["weight_correlation"] == 0.0


def test_per_cycle_overlap_skips_cycles_with_no_s1_decision():
    # S4 compra ogni 15 min, S1 no. Senza una decisione S1, non c'e' ciclo
    # di confronto: la misura risponde alla domanda dell'issue, non al
    # rumore di S4.
    s1: list[dict] = []
    s4 = [_s4_buy("AAPL", 0.020, _ts(2026, 8, 1, 13, 30))]

    assert compute_per_cycle_overlap(s1, s4, timedelta(days=30)) == []


def test_per_cycle_overlap_counts_s4_s1_rows_in_both_sleeves():
    # Una riga 'S4+S1' deve essere contata sia nel set S1 sia nel set S4
    # del ciclo (il tag contiene entrambi).
    s1 = [_s1_buy("AAPL", 0.012, _ts(2026, 8, 1, 14, 0))]
    s4 = [_s4_s1_buy("AAPL", 0.020, _ts(2026, 8, 1, 13, 30))]

    cycles = compute_per_cycle_overlap(s1, s4, timedelta(days=30))

    assert cycles[0]["n_s1"] == 1
    assert cycles[0]["n_s4"] == 1
    assert cycles[0]["jaccard"] == pytest.approx(1.0)


def test_per_cycle_overlap_keeps_both_sides_independent_when_disjoint():
    s1 = [_s1_buy("AAPL", 0.012, _ts(2026, 8, 1, 14, 0))]
    s4 = [_s4_buy("MSFT", 0.020, _ts(2026, 8, 1, 13, 30))]

    cycles = compute_per_cycle_overlap(s1, s4, timedelta(days=30))

    assert cycles[0]["n_s1"] == 1
    assert cycles[0]["n_s4"] == 1
    assert cycles[0]["jaccard"] == 0.0
    # Universo disgiunto → correlazione -1.0 (vettori "speculari" sul
    # supporto, uno dei due costantemente a zero sull'altro ticker).
    assert cycles[0]["weight_correlation"] == pytest.approx(-1.0)


def test_per_cycle_overlap_weight_correlation_high_with_two_shared_tickers():
    # Caso reale: due ticker condivisi, pesi che si muovono insieme.
    s1 = [
        _s1_buy("AAPL", 0.012, _ts(2026, 8, 1, 14, 0)),
        _s1_buy("MSFT", 0.020, _ts(2026, 8, 1, 14, 0)),
    ]
    s4 = [
        _s4_buy("AAPL", 0.020, _ts(2026, 8, 1, 13, 30)),
        _s4_buy("MSFT", 0.030, _ts(2026, 8, 1, 13, 30)),
    ]

    cycles = compute_per_cycle_overlap(s1, s4, timedelta(days=30))

    assert cycles[0]["n_s1"] == 2
    assert cycles[0]["n_s4"] == 2
    assert cycles[0]["jaccard"] == pytest.approx(1.0)
    # Pesi entrambi crescenti su AAPL→MSFT → correlazione +1.
    assert cycles[0]["weight_correlation"] == pytest.approx(1.0)


# ── 5. Classificazione del disaccordo (terzo affinamento dell'issue) ──────────


def test_classify_disagreement_distinguishes_buy_from_buy_or_sell():
    # S4 compra AAPL. Nello stesso ciclo S1 ha solo BUY di altri ticker
    # (nessuna entry su AAPL, nessuna uscita): "S4 compra cio' che S1 ignora".
    s1_cycle = [_s1_buy("MSFT", 0.012, _ts(2026, 8, 1, 14, 0))]
    s4_cycle = [_s4_buy("AAPL", 0.020, _ts(2026, 8, 1, 13, 30))]
    s1_sells: list[dict] = []

    result = classify_disagreement(s1_cycle, s4_cycle, s1_sells)

    assert result == {
        "s4_unique": ["AAPL"],
        "s1_unique": ["MSFT"],
        "s4_buys_against_s1_sells": [],
    }


def test_classify_disagreement_flags_buy_against_recent_sell():
    # S4 compra AAPL, S1 ha un SELL su AAPL nello stesso ciclo: e' il
    # reversal S1↔S4 (coda #182, perdita −$83.86 il 2026-07-16). Deve
    # essere classificato separatamente, non dentro "S4 compra cio' che
    # S1 ignora".
    s1_cycle = [_s1_buy("MSFT", 0.012, _ts(2026, 8, 1, 14, 0))]
    s4_cycle = [_s4_buy("AAPL", 0.020, _ts(2026, 8, 1, 13, 30))]
    s1_sells = [
        {
            "tick_time": _ts(2026, 8, 1, 14, 0),
            "symbol": "AAPL",
            "decision": "SELL",
        }
    ]

    result = classify_disagreement(s1_cycle, s4_cycle, s1_sells)

    assert result["s4_buys_against_s1_sells"] == ["AAPL"]
    assert "AAPL" not in result["s4_unique"]


# ── 6. Lo script non si spaccia per il connettore DB ─────────────────────────


def test_sleeve_attribution_does_not_assume_presence_of_signal_id():
    # I BUY S1 NON hanno signal_id, i BUY S4 SI. Lo script deve partire
    # sempre dalla colonna `reason` per non confondere le righe S1 con
    # S4 (un S1 BUY senza signal_id verrebbe scartato se ci si basasse
    # solo su signal_id). E' la verifica di attribuzione richiesta dalla
    # DoD: "L'attribuzione delle righe alle sleeve e' verificata, non
    # assunta".
    from scripts.measure_181_overlap import split_by_sleeve

    rows = [
        _s1_buy("AAPL", 0.012, _ts(2026, 8, 1, 14, 0)),
        _s4_buy("MSFT", 0.020, _ts(2026, 8, 1, 13, 30)),
    ]

    s1, s4 = split_by_sleeve(rows)

    # La riga S1 (senza signal_id) NON deve finire in S4.
    assert {row["symbol"] for row in s1} == {"AAPL"}
    assert {row["symbol"] for row in s4} == {"MSFT"}


def test_split_by_sleeve_assigns_s4_s1_to_both_sides():
    # Una riga 'S4+S1' deve essere contata in entrambe le sleeve.
    rows = [_s4_s1_buy("GOOG", 0.020, _ts(2026, 8, 1, 13, 30))]

    s1, s4 = split_by_sleeve(rows)

    assert {row["symbol"] for row in s1} == {"GOOG"}
    assert {row["symbol"] for row in s4} == {"GOOG"}
