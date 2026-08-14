"""#181: misura dell'overlap S1∩S4 sui target per ciclo di portfolio.

L'issue chiede di capire se l'overlay S4 conferma S1 o gli duplica il
book. Quattro affinamenti specificati dall'issue che i test inchiodano:

  1. Jaccard degli insiemi di ticker con peso target > 0, per ciclo di
     portfolio (non un singolo aggregato).
  2. Correlazione dei pesi target — due sleeve possono toccare gli
     stessi ticker con pesi molto diversi.
  3. Confronto con il baseline atteso da selezione casuale, viste le
     diverse dimensioni delle sleeve.
  4. Classificazione del disaccordo:
       - "S4 tiene a target ciò che S1 ignora"
       - "S4 tiene a target ciò che S1 sta uscendo" (reversal, #182)

**L'oggetto misurato è il target, non l'evento di ingresso.** È la
distinzione che questi test difendono: un ticker che entrambe le sleeve
vogliono tenere non produce un secondo BUY, perché il guard
anti-pyramiding (P0-05) scarta l'ordine quando la posizione è già a
libro. Una misura costruita sui BUY trova quindi ~zero overlap per
costruzione — misura il complemento di ciò che l'issue chiede.

L'attribuzione S1/S4 non e' assunta: la verifica e' parte della DoD, e
deve reggere su tutte le forme di `reason` scritte da
`portfolio_scheduler.py` (non solo i prefissi di ingresso: anche
`[s1_weight_drop] S1 ...`, `[expired] S4 ...`, `S4+S1 ...`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.measure_181_overlap import (
    anti_pyramiding_censoring,
    assign_to_cycle,
    attribution_audit,
    classify_disagreement,
    compute_target_overlap_per_cycle,
    expected_jaccard_random_baseline,
    jaccard,
    riepiloga,
    sleeves_of_reason,
    split_by_sleeve,
    weight_correlation,
)


# ── helpers minimi, niente DB, niente datetime.now() ──────────────────────────


def _ts(year: int, month: int, day: int, hour: int = 17, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


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


def _s4_blocked(symbol: str, weight: float, ts: datetime) -> dict:
    """BUY S4 fermato dal guard anti-pyramiding: il ticker resta un target
    di S4 anche se non diventa mai un ordine (riga #231)."""
    return {
        "tick_time": ts,
        "symbol": symbol,
        "decision": "SKIP_PYRAMIDING",
        # Il reason NON nomina la sleeve, come in produzione: e' esattamente il
        # motivo per cui esiste il fallback su `signal_score`. Con "S4" nel testo
        # l'attribuzione passerebbe dal ramo testuale e il fallback resterebbe
        # non esercitato — il test sembrerebbe verde senza verificare nulla.
        "reason": (
            "P0-05 anti-pyramiding: gia' a libro dal 2026-07-14, sentiment +0.396, "
            "peso non allocato 2.3%."
        ),
        "score": weight,
        "signal_score": 0.396,
        "signal_id": 12345,
    }


def _s1_blocked(symbol: str, weight: float, ts: datetime) -> dict:
    """Blocco anti-pyramiding SENZA `signal_score`: e' l'altra meta' del
    fallback, e senza questo caso il ramo S1 non verrebbe mai percorso."""
    return {
        "tick_time": ts,
        "symbol": symbol,
        "decision": "SKIP_PYRAMIDING",
        "reason": "P0-05 anti-pyramiding: gia' a libro dal 2026-07-14, peso non allocato 1.2%.",
        "score": weight,
        "signal_score": None,
        "signal_id": None,
    }


def _s1_exit(symbol: str, ts: datetime) -> dict:
    return {
        "tick_time": ts,
        "symbol": symbol,
        "decision": "SELL",
        "reason": "[s1_weight_drop] S1 target weight dropped to 0% — position closed.",
        "score": 0.0,
        "signal_id": None,
    }


def _pos(symbol: str, sleeve_reason: str, entry: datetime, weight: float, exit_: datetime | None = None) -> dict:
    return {
        "symbol": symbol,
        "entry_time": entry,
        "exit_time": exit_,
        "score": weight,
        "reason": sleeve_reason,
    }


_S1_REASON = "S1 momentum: time-series momentum signal, portfolio weight 2.5%."
_S4_REASON = "S4 news-driven: sentiment +0.500 (ensemble), portfolio weight 2.0%."


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
    # sul vuoto. Il riepilogo tiene questi cicli fuori dalle medie.
    assert jaccard(set(), set()) == 1.0


# ── 2. Correlazione pesata — distinta dalla Jaccard ──────────────────────────


def test_weight_correlation_high_when_weights_track():
    # Stesso ticker, pesi entrambi con varianza: correlazione +1.
    s1 = {"AAPL": 0.012, "MSFT": 0.020}
    s4 = {"AAPL": 0.014, "MSFT": 0.024}
    assert weight_correlation(s1, s4) == pytest.approx(1.0)


def test_weight_correlation_zero_when_one_sleeve_has_constant_weight():
    # S4 mette lo stesso peso su tutti i ticker: la deviazione standard
    # e' zero, e per convenzione (definizione di Pearson con sd=0)
    # ritorniamo 0.0.
    s1 = {"AAPL": 0.012, "MSFT": 0.014}
    s4 = {"AAPL": 0.020, "MSFT": 0.020}
    assert weight_correlation(s1, s4) == 0.0


def test_weight_correlation_negative_on_disjoint():
    # Universo disgiunto: S1 mette peso dove S4 NON mette peso.
    s1 = {"AAPL": 0.012}
    s4 = {"GOOG": 0.020}
    assert weight_correlation(s1, s4) == pytest.approx(-1.0)


def test_weight_correlation_inverted_means_overlap_with_opposite_size():
    s1 = {"AAPL": 0.020, "MSFT": 0.010}
    s4 = {"AAPL": 0.010, "MSFT": 0.020}
    assert weight_correlation(s1, s4) == pytest.approx(-1.0)


# ── 3. Baseline atteso da selezione casuale ──────────────────────────────────


def test_baseline_jaccard_with_equal_sleeves_and_full_universe():
    baseline = expected_jaccard_random_baseline(n_universe=96, n_s1=10, n_s4=10)
    expected = (100 / 96) / (20 - 100 / 96)
    assert baseline == pytest.approx(expected)
    assert baseline < 0.2  # sanity: e' un overlap piccolo per costruzione


def test_baseline_jaccard_scales_with_sleeve_size():
    small = expected_jaccard_random_baseline(n_universe=96, n_s1=5, n_s4=5)
    big = expected_jaccard_random_baseline(n_universe=96, n_s1=20, n_s4=20)
    assert big > small


# ── 4. Attribuzione delle sleeve: verificata, non assunta ────────────────────


def test_sleeve_attribution_does_not_assume_presence_of_signal_id():
    # I BUY S1 NON hanno signal_id, i BUY S4 SI. Lo script deve partire
    # sempre dalla colonna `reason` per non confondere le righe S1 con
    # S4 (un S1 BUY senza signal_id verrebbe scartato se ci si basasse
    # solo su signal_id).
    rows = [
        _s1_buy("AAPL", 0.012, _ts(2026, 8, 1, 14, 0)),
        _s4_buy("MSFT", 0.020, _ts(2026, 8, 1, 13, 30)),
    ]

    s1, s4 = split_by_sleeve(rows)

    assert {row["symbol"] for row in s1} == {"AAPL"}
    assert {row["symbol"] for row in s4} == {"MSFT"}


def test_sleeve_attribution_covers_exit_reasons_not_only_entry_prefixes():
    # Le uscite S1 non iniziano con "S1": dal 2026-07-21 la forma viva e'
    # `[s1_weight_drop] S1 target weight dropped...`. Un'attribuzione che
    # guardasse solo il prefisso perderebbe 25 uscite su 30 e con esse la
    # classificazione dei reversal.
    assert sleeves_of_reason("[s1_weight_drop] S1 target weight dropped to 0% — position closed.") == frozenset({"S1"})
    assert sleeves_of_reason("[expired] S4 signal expired (age=4.4h > max_age=4h)") == frozenset({"S4"})
    assert sleeves_of_reason("[whipsaw] Portfolio rebalance: weight 0.0% — S4 signal present") == frozenset({"S4"})
    assert sleeves_of_reason("S4+S1 news-driven: sentiment +0.5") == frozenset({"S1", "S4"})


def test_sleeve_attribution_leaves_unattributable_rows_out():
    # Una chiusura di rischio o un ribilanciamento generico non appartiene
    # ad alcuna sleeve: contarla come S1 o S4 falserebbe entrambi i lati.
    assert sleeves_of_reason("Portfolio rebalance: weight 0.0%.") == frozenset()
    assert sleeves_of_reason("stop_loss: MRK px 121.30 <= stop 122.10") == frozenset()
    assert sleeves_of_reason("") == frozenset()


def test_attribution_audit_reports_unattributed_reasons():
    decisions = [
        _s1_buy("AAPL", 0.02, _ts(2026, 8, 1)),
        {
            "tick_time": _ts(2026, 8, 1),
            "symbol": "MRK",
            "decision": "SELL",
            "reason": "stop_loss: MRK px 121.30 <= stop 122.10",
            "score": 0.0,
            "signal_id": None,
        },
    ]

    audit = attribution_audit(decisions, [])

    assert audit["righe_per_sleeve"]["S1"] == 1
    assert audit["righe_per_sleeve"]["nessuna"] == 1
    assert any("stop_loss" in r for r in audit["reason_non_attribuibili"])


# ── 5. Il ciclo e' il ciclo di portfolio, non una finestra inventata ─────────


def test_decision_is_assigned_to_the_cycle_that_precedes_it():
    # Le righe di decisione sono scritte qualche secondo dopo il ciclo che
    # le ha prodotte (le SKIP_PYRAMIDING a fine ciclo, #231): un confronto
    # per uguaglianza esatta del timestamp le perderebbe tutte.
    cycles = [_ts(2026, 8, 12, 19, 37), _ts(2026, 8, 12, 19, 52)]

    assert assign_to_cycle(_ts(2026, 8, 12, 19, 52, 9), cycles) == _ts(2026, 8, 12, 19, 52)


def test_decision_far_from_any_cycle_is_dropped():
    # Meglio scartare che attribuire al ciclo sbagliato.
    cycles = [_ts(2026, 8, 12, 19, 37)]

    assert assign_to_cycle(_ts(2026, 8, 12, 23, 0), cycles) is None
    assert assign_to_cycle(_ts(2026, 8, 12, 10, 0), cycles) is None


# ── 6. Target per ciclo — il cuore della misura ──────────────────────────────


def test_open_position_stays_in_the_target_set_without_any_new_buy():
    # S1 compra AAPL al primo ciclo e non emette piu' nulla: il ticker
    # resta il suo target anche nei cicli successivi. Una misura basata
    # sui soli eventi BUY vedrebbe un book vuoto dal secondo ciclo.
    cycles = [_ts(2026, 8, 3, 14, 0), _ts(2026, 8, 3, 14, 15), _ts(2026, 8, 3, 14, 30)]
    positions = [_pos("AAPL", _S1_REASON, _ts(2026, 8, 3, 14, 0), 0.025)]

    serie = compute_target_overlap_per_cycle(cycles, positions, [])

    assert [c["n_s1"] for c in serie] == [1, 1, 1]
    assert serie[-1]["s1_symbols"] == ["AAPL"]


def test_blocked_s4_intent_on_a_name_s1_already_holds_counts_as_overlap():
    # IL CASO CHE LA MISURA DEVE VEDERE. S1 tiene AMD da luglio; S4 vuole
    # comprarla, il guard anti-pyramiding blocca l'ordine. Non esiste
    # alcun BUY S4 su AMD — eppure le due sleeve hanno lo stesso target.
    cycles = [_ts(2026, 8, 11, 14, 37)]
    positions = [_pos("AMD", _S1_REASON, _ts(2026, 7, 14, 15, 0), 0.023)]
    decisions = [_s4_blocked("AMD", 0.023, _ts(2026, 8, 11, 14, 37, 8))]

    serie = compute_target_overlap_per_cycle(cycles, positions, decisions)

    assert serie[0]["s1_symbols"] == ["AMD"]
    assert serie[0]["s4_symbols"] == ["AMD"]
    assert serie[0]["jaccard"] == pytest.approx(1.0)
    assert serie[0]["n_intersezione"] == 1


def test_position_leaves_the_target_set_after_its_exit():
    cycles = [_ts(2026, 8, 3, 14, 0), _ts(2026, 8, 4, 14, 0)]
    positions = [
        _pos("AAPL", _S1_REASON, _ts(2026, 8, 3, 13, 0), 0.025, exit_=_ts(2026, 8, 3, 20, 0))
    ]

    serie = compute_target_overlap_per_cycle(cycles, positions, [])

    assert serie[0]["s1_symbols"] == ["AAPL"]
    assert serie[1]["s1_symbols"] == []


def test_s4_s1_position_counts_in_both_sleeves():
    # Una posizione aperta da una riga 'S4+S1' e' target di entrambe.
    cycles = [_ts(2026, 8, 3, 14, 0)]
    positions = [
        _pos("WDC", "S4+S1 news-driven: sentiment +0.5, portfolio weight 2.0%.", _ts(2026, 7, 21), 0.02)
    ]

    serie = compute_target_overlap_per_cycle(cycles, positions, [])

    assert serie[0]["s1_symbols"] == ["WDC"]
    assert serie[0]["s4_symbols"] == ["WDC"]


def test_disjoint_books_give_zero_jaccard_and_full_disagreement():
    cycles = [_ts(2026, 8, 3, 14, 0)]
    positions = [
        _pos("AAPL", _S1_REASON, _ts(2026, 7, 20), 0.025),
        _pos("SPCX", _S4_REASON, _ts(2026, 8, 1), 0.020),
    ]

    serie = compute_target_overlap_per_cycle(cycles, positions, [])

    assert serie[0]["jaccard"] == 0.0
    assert serie[0]["s4_unique_count"] == 1
    assert serie[0]["s1_unique_count"] == 1


def test_weight_correlation_uses_the_latest_target_weight_seen():
    # Il peso di una posizione a libro e' quello del suo ultimo intento,
    # non quello congelato all'ingresso: e' cio' che la sleeve vuole ora.
    #
    # Il test deve FALLIRE se l'aggiornamento del peso viene rimosso, quindi
    # entrambe le sleeve tengono gli stessi due nomi con pesi diversi fra loro:
    # al primo ciclo i due vettori coincidono (correlazione 1), e solo
    # l'applicazione dell'intento S1 su AMD li fa divergere nel secondo.
    # Senza l'aggiornamento, il secondo ciclo resterebbe identico al primo.
    # Servono TRE cicli. Con due soli, il peso aggiornato arriverebbe comunque
    # dal ramo che applica l'intento del ciclo corrente, e il test non
    # distinguerebbe: cio' che va verificato e' che il peso PERSISTA nei cicli
    # successivi, quando l'intento non e' piu' quello corrente.
    cycles = [_ts(2026, 8, 3, 14, 0), _ts(2026, 8, 3, 14, 15), _ts(2026, 8, 3, 14, 30)]
    positions = [
        _pos("AMD", "S4+S1 news-driven: sentiment +0.5, portfolio weight 1.0%.",
             _ts(2026, 7, 14), 0.010),
        _pos("NOK", "S4+S1 news-driven: sentiment +0.5, portfolio weight 3.0%.",
             _ts(2026, 7, 14), 0.030),
    ]
    decisions = [_s1_buy("AMD", 0.040, _ts(2026, 8, 3, 14, 15, 5))]

    serie = compute_target_overlap_per_cycle(cycles, positions, decisions)

    assert serie[2]["n_s1"] == 2
    # Primo ciclo: nessun intento visto, i due vettori coincidono.
    assert serie[0]["weight_correlation"] == pytest.approx(1.0)
    # TERZO ciclo: l'intento e' vecchio di un ciclo. Se il peso non persistesse,
    # AMD tornerebbe a 0.010 e la correlazione risalirebbe a 1.0.
    assert serie[2]["weight_correlation"] < 0.0


def test_cycles_without_any_target_are_excluded_from_the_summary_means():
    # La Jaccard del vuoto e' 1 per convenzione: se entrasse nelle medie,
    # un mese di cicli fuori mercato racconterebbe un overlap perfetto.
    cycles = [_ts(2026, 8, 3, 14, 0), _ts(2026, 8, 4, 14, 0)]
    positions = [
        _pos("AAPL", _S1_REASON, _ts(2026, 8, 4, 13, 0), 0.025),
    ]

    serie = compute_target_overlap_per_cycle(cycles, positions, [])
    riepilogo = riepiloga(serie, universe_size=96)

    assert riepilogo["n_cicli"] == 2
    assert riepilogo["n_cicli_con_target"] == 1
    assert riepilogo["jaccard_media"] == 0.0


# ── 7. Classificazione del disaccordo (terzo affinamento dell'issue) ─────────


def test_classify_disagreement_distinguishes_ignored_from_sold():
    # S4 tiene AAPL a target. S1 ha altri nomi e non sta uscendo da AAPL:
    # e' "S4 tiene cio' che S1 ignora".
    result = classify_disagreement(s1_targets={"MSFT"}, s4_targets={"AAPL"}, s1_exits=set())

    assert result == {
        "s4_unique": ["AAPL"],
        "s1_unique": ["MSFT"],
        "s4_targets_against_s1_exits": [],
    }


def test_classify_disagreement_flags_target_against_s1_exit():
    # S4 tiene AAPL a target mentre S1 la sta uscendo nello stesso ciclo:
    # e' il reversal S1↔S4 (coda #182, perdita −$83.86 il 2026-07-16).
    # Va classificato separatamente, non dentro "S4 tiene cio' che S1
    # ignora".
    result = classify_disagreement(
        s1_targets={"MSFT"}, s4_targets={"AAPL"}, s1_exits={"AAPL"}
    )

    assert result["s4_targets_against_s1_exits"] == ["AAPL"]
    assert "AAPL" not in result["s4_unique"]


def test_reversal_is_detected_on_the_series_from_an_s1_exit_row():
    cycles = [_ts(2026, 8, 3, 14, 0)]
    positions = [_pos("AAPL", _S4_REASON, _ts(2026, 8, 1), 0.020)]
    decisions = [_s1_exit("AAPL", _ts(2026, 8, 3, 14, 0, 7))]

    serie = compute_target_overlap_per_cycle(cycles, positions, decisions)

    assert serie[0]["reversal_symbols"] == ["AAPL"]
    assert serie[0]["reversal_count"] == 1


# ── 8. La censura del guard va misurata, non solo dichiarata ────────────────


def test_censoring_counts_s4_intents_landing_on_names_s1_already_holds():
    # Senza questo numero, un overlap realizzato ~0 si legge come "le due
    # sleeve scelgono nomi diversi", mentre puo' essere solo il guard
    # anti-pyramiding che impedisce la seconda entrata.
    positions = [_pos("AMD", _S1_REASON, _ts(2026, 7, 14), 0.023)]
    decisions = [
        _s4_blocked("AMD", 0.023, _ts(2026, 8, 11, 14, 37, 8)),
        _s4_buy("SPCX", 0.020, _ts(2026, 8, 12, 18, 52)),
    ]

    censura = anti_pyramiding_censoring(decisions, positions)

    assert censura["intenti_ingresso_s4"] == 2
    assert censura["intenti_fermati_dal_guard"] == 1
    assert censura["intenti_su_nomi_gia_a_libro_s1"] == 1
    assert censura["quota_intenti_su_nomi_s1"] == pytest.approx(0.5)
    assert censura["simboli"] == ["AMD"]


def test_censoring_ignores_intents_before_the_uncensored_window():
    # Prima del 2026-08-11 le righe SKIP_PYRAMIDING non esistono: contare
    # i soli BUY di quel periodo darebbe una quota falsa (zero per
    # costruzione).
    positions = [_pos("AMD", _S1_REASON, _ts(2026, 7, 1), 0.023)]
    decisions = [_s4_buy("AMD", 0.020, _ts(2026, 7, 20, 15, 0))]

    censura = anti_pyramiding_censoring(decisions, positions)

    assert censura["intenti_ingresso_s4"] == 0
    assert censura["quota_intenti_su_nomi_s1"] is None


def test_split_by_sleeve_assigns_s4_s1_to_both_sides():
    rows = [
        {
            "tick_time": _ts(2026, 8, 1, 13, 30),
            "symbol": "GOOG",
            "decision": "BUY",
            "reason": "S4+S1 news-driven: sentiment +0.500 (ensemble), portfolio weight 2.0%.",
            "score": 0.02,
            "signal_id": 12345,
        }
    ]

    s1, s4 = split_by_sleeve(rows)

    assert {row["symbol"] for row in s1} == {"GOOG"}
    assert {row["symbol"] for row in s4} == {"GOOG"}


def test_split_by_sleeve_includes_blocked_entry_intents():
    # Anche la misura secondaria (coincidenza degli eventi) deve contare
    # l'intento fermato dal guard: e' un ingresso voluto, non un non-evento.
    rows = [_s4_blocked("AMD", 0.023, _ts(2026, 8, 11, 14, 37, 8))]

    _, s4 = split_by_sleeve(rows)

    assert {row["symbol"] for row in s4} == {"AMD"}


def test_blocked_entry_without_signal_score_is_attributed_to_s1():
    # L'altra meta' del fallback strutturale: `signal_score` viene valorizzato
    # solo per gli ordini con tag S4, quindi un blocco che ne e' privo viene
    # dall'unica altra sleeve viva. Senza questo caso il ramo S1 del fallback
    # non verrebbe mai percorso da nessun test.
    rows = [_s1_blocked("AMD", 0.012, _ts(2026, 8, 11, 14, 37, 8))]

    s1, s4 = split_by_sleeve(rows)

    assert {row["symbol"] for row in s1} == {"AMD"}
    assert s4 == []
