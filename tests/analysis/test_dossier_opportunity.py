"""Stimatore v2 di alpha accessibile e costo per il dossier alpha-miss (#280).

Modulo puro sotto test: `src.analysis.dossier.opportunity`. Versiona la formula,
dichiara cutoff/entry/exit/size/vincoli/costi/formula/estimator_version per ogni
stima, tiene separati gli importi misurati/attribuiti/congetturali e non tratta
titoli tematicamente simili come fungibili.

La parte intraday (prezzare l'entry al primo ciclo realmente eleggibile) e'
disponibile solo quando il dossier fornisce barre intraday + eligible_cycle_at
(issue #277, non ancora in main): lo stimatore e' intraday-ready ma degrada con
missingness esplicita quando quei dati mancano, senza mai confondere gross con
accessible.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.dossier.opportunity import ESTIMATOR_VERSION, compute_opportunity


def _daily(open_, high, low, close, close_prec):
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "close_prec": close_prec,
    }


def test_gross_opportunity_e_dichiara_tutti_i_campi_obbligatori():
    """Gross = |close/close_prec - 1| * size; la stima porta estimator_version e formula."""
    # ORCL 12/08: close_prec 111.30 -> close 117.95 (+5.36%). Size S4 ~2200$.
    est = compute_opportunity(
        {
            "symbol": "ORCL",
            "book_side": "long",
            "held": False,
            "daily": _daily(116.0, 118.0, 115.0, 117.95, 111.30),
            "size_usd": 2200.0,
            "slot_fraction": 0.02,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    rendimento = 117.95 / 111.30 - 1.0
    assert est["gross_opportunity_usd"] == pytest.approx(abs(rendimento) * 2200.0)
    # Criterio d'accettazione 1: ogni stima dichiara i campi obbligatori.
    assert est["estimator_version"] == ESTIMATOR_VERSION
    for campo in ("cutoff", "entry", "exit", "size", "vincoli", "costi", "formula"):
        assert campo in est, f"manca {campo}"
    assert est["confidenza"] == "congetturale"


def test_ribasso_non_detenuto_long_only_h_costo_zero_verificato_non_null():
    """Criterio 2: un ribasso non detenuto in book long-only ha accessible/net = 0.0
    verificato, NON null. Non possiamo vendere allo scoperto: il ribasso non era
    catturabile. Null vorrebbe dire 'non stimato', che e' un'affermazione diversa."""
    est = compute_opportunity(
        {
            "symbol": "META",
            "book_side": "long",
            "held": False,
            "daily": _daily(190.0, 192.0, 184.0, 184.0, 195.0),  # -5.6%
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    assert est["accessible_opportunity_usd"] == 0.0
    assert est["net_opportunity_usd"] == 0.0
    # costo zero *verificato*, non null: distingue "innocuo" da "non stimato".
    assert est["costi"]["total_usd"] == 0.0
    assert est["entry"]["missing_reason"] == "long_only_no_short_downside_not_held"
    # gross resta il full move (utile per directional accuracy), ma e' label-opposto
    assert est["gross_opportunity_usd"] is not None and est["gross_opportunity_usd"] > 0.0


def test_rialzo_non_detenuto_con_intraday_accessible_dal_primo_ciclo_eleggibile():
    """Con barre intraday + eligible_cycle_at (#277), accessible = (exit_close -
    entry_open_al_ciclo) x shares; net = accessible - roundtrip_cost.

    Modella ORCL 12/08: quasi tutto il movimento nel gap pre-market, solo ~$6,82
    catturabili dal primo ciclo realmente eleggibile contro ~$117,95 close-to-close.
    """
    # close_prec 111.30 -> close 117.95 (+5.95%). open 117.00 (gap gia' consumato).
    daily = _daily(117.00, 118.50, 116.50, 117.95, 111.30)
    # Primo ciclo eleggibile alle 14:00 UTC; primo bar alle 14:05 open 117.10.
    bars = [
        {"timestamp": "2026-08-12T13:55:00+00:00", "open": 116.90, "high": 117.0,
         "low": 116.8, "close": 117.0},  # prima del ciclo: ignorato
        {"timestamp": "2026-08-12T14:05:00+00:00", "open": 117.10, "high": 118.0,
         "low": 117.0, "close": 117.6},  # primo bar PIT >= ciclo
    ]
    size = 2200.0
    est = compute_opportunity(
        {
            "symbol": "ORCL",
            "book_side": "long",
            "held": False,
            "daily": daily,
            "intraday_bars": bars,
            "eligible_cycle_at": "2026-08-12T14:00:00+00:00",
            "size_usd": size,
            "slot_fraction": 0.02,
            "cost": {"total_usd": 1.30, "spread_bps": 5.0, "impact_bps": 0.4,
                     "regulatory_usd": 0.5, "model": "TradeCostCalculator/cost_model.yaml",
                     "adv_source": "default_fallback"},
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    shares = size / 117.10
    accessible = (117.95 - 117.10) * shares
    assert est["accessible_opportunity_usd"] == pytest.approx(accessible)
    assert est["net_opportunity_usd"] == pytest.approx(accessible - 1.30)
    # gross e' il full close-to-close, molto piu grande di accessible: NON confusi.
    gross = abs(117.95 / 111.30 - 1.0) * size
    assert est["gross_opportunity_usd"] == pytest.approx(gross)
    # gross (close-to-close) materialmente piu grande di accessible (intraday):
    # la quota prezzata al ciclo e' una frazione del full move — NON confusi.
    assert est["gross_opportunity_usd"] > est["accessible_opportunity_usd"] * 5
    # entry prezzato sul primo bar PIT >= ciclo, non su quello prima.
    assert est["entry"]["price"] == 117.10
    assert est["entry"]["bar_timestamp"] == "2026-08-12T14:05:00+00:00"
    assert est["exit"]["price"] == 117.95


def test_rialzo_senza_intraday_accessible_null_con_missingness_non_confuso_con_gross():
    """Senza barre intraday (oggi, #277 non in main) accessible e' None con
    missingness esplicita. gross resta calcolato come upper bound, ma net e' None:
    mai uguale a gross, mai inventato."""
    est = compute_opportunity(
        {
            "symbol": "ORCL",
            "book_side": "long",
            "held": False,
            "daily": _daily(117.00, 118.50, 116.50, 117.95, 111.30),
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    assert est["accessible_opportunity_usd"] is None
    assert est["net_opportunity_usd"] is None
    assert "intraday_bars_not_available_eligible_cycle_unpriced" in est["missingness"]
    assert est["gross_opportunity_usd"] is not None  # upper bound calcolato
    assert est["costi"]["total_usd"] is None


def test_nessuna_fungibilita_tematica_senza_regola_preregistrata():
    """Criterio 4: lo stimatore non netta esposizioni tematiche (es. MU/NOK da ORCL).
    fungibility_rule = "none" e non esiste campo che sottragga un offset cross-ticker."""
    est = compute_opportunity(
        {
            "symbol": "ORCL",
            "book_side": "long",
            "held": False,
            "daily": _daily(117.00, 118.50, 116.50, 117.95, 111.30),
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "confidenza": "congetturale",
        }
    )
    assert est["fungibility_rule"] == "none — per-ticker, nessuna sostituzione tematica"
    # Nessun campo di offset tematico: la stima e' entirely per-ticker.
    assert "thematic_offset" not in est
    assert "net_thematic" not in est


def test_confidenza_riportata_e_non_mescolata():
    """Criterio 3: ogni stima porta una singola confidenza; gross/accessible/net
    restano campi separati, non sommati in un unico dollaro 'congetturale'."""
    est = compute_opportunity(
        {
            "symbol": "X",
            "book_side": "long",
            "held": False,
            "daily": _daily(100.0, 105.0, 99.0, 104.0, 100.0),
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "confidenza": "congetturale",
        }
    )
    assert est["confidenza"] == "congetturale"
    # I tre livelli restano distinti come campi, non fusi in un totale.
    for campo in ("gross_opportunity_usd", "accessible_opportunity_usd", "net_opportunity_usd"):
        assert campo in est
    assert "total_opportunity_usd" not in est


def test_posizione_detenuta_non_e_un_miss_accessibile_null():
    """Un titolo gia' in portafoglio non e' un alpha-miss: l'opportunita' e'
    esposizione passiva (M4), non una stima congetturale qui. accessible = None."""
    est = compute_opportunity(
        {
            "symbol": "NVDA",
            "book_side": "long",
            "held": True,
            "daily": _daily(130.0, 134.0, 129.0, 133.0, 128.0),
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "confidenza": "misurata",
        }
    )
    assert est["accessible_opportunity_usd"] is None
    assert est["entry"]["missing_reason"] == "held_position_not_an_alpha_miss"


def test_pit_bar_dopo_cutoff_ignorato_e_bar_prima_del_ciclo_ignorato():
    """No look-ahead: l'entry usa solo il primo bar con apertura in
    [eligible_cycle_at, cutoff]. Un bar prima del ciclo o dopo il cutoff non vale."""
    daily = _daily(100.0, 110.0, 99.0, 108.0, 100.0)
    bars = [
        {"timestamp": "2026-08-12T13:55:00+00:00", "open": 100.5, "high": 101,
         "low": 100, "close": 101},  # prima del ciclo
        {"timestamp": "2026-08-12T20:30:00+00:00", "open": 109.0, "high": 110,
         "low": 108, "close": 108},  # dopo il cutoff (20:00) -> ignorato
    ]
    est = compute_opportunity(
        {
            "symbol": "X",
            "book_side": "long",
            "held": False,
            "daily": daily,
            "intraday_bars": bars,
            "eligible_cycle_at": "2026-08-12T14:00:00+00:00",
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "confidenza": "congetturale",
        }
    )
    # Nessun bar in [14:00, 20:00] -> accessible None con missingness esplicita.
    assert est["accessible_opportunity_usd"] is None
    assert "no_intraday_bar_in_eligible_window" in est["missingness"]


def test_trade_simulato_a_pareggio_subisce_il_costo_roundtrip():
    """Un trade realmente simulato con entry == exit (P&L lordo 0) deve comunque
    portarsi dietro il costo roundtrip: net = 0 - cost = -cost, non 0.

    Distingue 'ho eseguito il trade a pareggio' (costo reale) da 'long-only,
    ribasso, non detenuto' (no trade possibile, costo zero verificato). Il bug
    storico (opportunity.py riga 299) collassava entrambi i casi in accessible=0
    -> costo 0 / net 0: i test coprivano solo il caso long-only, mancava il caso
    'trade simulato a pareggio'.
    """
    # Rialzo close_prec 100 -> close 110 (+10%). open 110.00 (gap gia' consumato).
    daily = _daily(110.0, 111.0, 109.0, 110.0, 100.0)
    # Primo bar PIT al ciclo: open 110.00 = close 110.00 -> P&L lordo 0 ma trade c'e'.
    bars = [
        {"timestamp": "2026-08-12T13:55:00+00:00", "open": 105.0, "high": 106.0,
         "low": 104.0, "close": 106.0},  # prima del ciclo: ignorato
        {"timestamp": "2026-08-12T14:05:00+00:00", "open": 110.0, "high": 110.2,
         "low": 109.8, "close": 110.0},  # entry == exit -> P&L lordo 0
    ]
    size = 2200.0
    cost = {"total_usd": 1.30, "spread_bps": 5.0, "impact_bps": 0.4,
            "regulatory_usd": 0.5, "model": "TradeCostCalculator/cost_model.yaml",
            "adv_source": "default_fallback"}
    est = compute_opportunity(
        {
            "symbol": "XYZ",
            "book_side": "long",
            "held": False,
            "daily": daily,
            "intraday_bars": bars,
            "eligible_cycle_at": "2026-08-12T14:00:00+00:00",
            "size_usd": size,
            "slot_fraction": 0.02,
            "cost": cost,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    # P&L lordo = (110 - 110) * shares = 0, MA il trade e' stato eseguito davvero.
    assert est["accessible_opportunity_usd"] == pytest.approx(0.0)
    # Il costo roundtrip va sottratto: net = 0 - 1.30 = -1.30.
    assert est["net_opportunity_usd"] == pytest.approx(-1.30)
    # Il blocco costi dichiara il roundtrip, NON 0.0.
    assert est["costi"]["total_usd"] == pytest.approx(1.30)
    assert est["costi"]["spread_bps"] == pytest.approx(5.0)
    # L'entry block non deve essere quello del 'no trade' long-only.
    assert est["entry"]["missing_reason"] is None
    assert est["entry"]["price"] == 110.0
    assert est["entry"]["bar_timestamp"] == "2026-08-12T14:05:00+00:00"


def test_trade_state_no_trade_vs_simulated_distinti_nel_return():
    """Lo stimatore deve dichiarare lo stato del trade cosi' l'orchestratore (e
    i futuri ledger) possono distinguere i due zeri semanticamente opposti:
    'no_trade' (long-only ribasso) e 'simulated' (ho eseguito davvero, anche a
    pareggio). Per oggi il campo e' documentato ma non esposto nel return pubblico
    di compute_opportunity: bastano le missing_reason e i costi per distinguerli."""
    # Caso 1: long-only ribasso -> costi 0.0, net 0.0, missing_reason long_only_*
    est_down = compute_opportunity(
        {
            "symbol": "META",
            "book_side": "long",
            "held": False,
            "daily": _daily(190.0, 192.0, 184.0, 184.0, 195.0),
            "size_usd": 2200.0,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "confidenza": "congetturale",
        }
    )
    assert est_down["entry"]["missing_reason"] == "long_only_no_short_downside_not_held"
    assert est_down["costi"]["total_usd"] == 0.0
    # Caso 2: trade simulato a pareggio -> costi dichiarati, net = -cost
    est_flat = compute_opportunity(
        {
            "symbol": "XYZ",
            "book_side": "long",
            "held": False,
            "daily": _daily(110.0, 111.0, 109.0, 110.0, 100.0),
            "intraday_bars": [
                {"timestamp": "2026-08-12T14:05:00+00:00", "open": 110.0,
                 "high": 110.2, "low": 109.8, "close": 110.0},
            ],
            "eligible_cycle_at": "2026-08-12T14:00:00+00:00",
            "size_usd": 2200.0,
            "cost": {"total_usd": 1.30, "spread_bps": 5.0, "impact_bps": 0.4,
                     "regulatory_usd": 0.5, "model": "x", "adv_source": "y"},
            "cutoff": "2026-08-12T20:00:00+00:00",
            "confidenza": "congetturale",
        }
    )
    # Stesso accessible == 0.0, ma costo opposto: il return li distingue.
    assert est_flat["entry"]["missing_reason"] is None
    assert est_flat["costi"]["total_usd"] == pytest.approx(1.30)

# --- #246: il wiring intraday e la serie legacy affiancata -------------------


def _bars_5min(prezzi: list[tuple[str, float]]) -> list[dict]:
    return [{"timestamp": ts, "open": p, "high": p, "low": p, "close": p}
            for ts, p in prezzi]


def test_accessible_ora_si_calcola_quando_barre_e_ciclo_sono_cablati():
    """Il caso ORCL 12/08: il close-to-close vale ~118$ di size, ma il tratto
    davvero catturabile dal primo ciclo eleggibile e' una frazione di quello."""
    est = compute_opportunity(
        {
            "symbol": "ORCL",
            "book_side": "long",
            "held": False,
            "daily": _daily(240.0, 246.0, 239.0, 245.0, 232.5),
            "intraday_bars": _bars_5min([
                ("2026-08-12T13:35:00+00:00", 241.0),   # pre-ciclo: non usabile
                ("2026-08-12T14:10:00+00:00", 244.25),  # primo bar >= ciclo
                ("2026-08-12T15:00:00+00:00", 244.8),
            ]),
            "eligible_cycle_at": "2026-08-12T14:07:00+00:00",
            "eligible_cycle_source": "session_open",
            "size_usd": 2200.0,
            "slot_fraction": 0.02,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    assert est["accessible_opportunity_usd"] is not None
    # entry sull'apertura del primo bar successivo al ciclo, non sulla barra 13:35
    assert est["entry"]["price"] == pytest.approx(244.25)
    assert est["entry"]["bar_timestamp"] == "2026-08-12T14:10:00+00:00"
    shares = 2200.0 / 244.25
    assert est["accessible_opportunity_usd"] == pytest.approx((245.0 - 244.25) * shares)
    # ...e resta molto sotto il gross close-to-close: e' la misura del #246.
    assert est["accessible_opportunity_usd"] < est["gross_opportunity_usd"] / 10


def test_la_fonte_del_ciclo_eleggibile_e_dichiarata_nella_stima():
    """`session_open` e `execution_decisions.tick_time` sono due popolazioni
    diverse: la stima porta la fonte, cosi' non si mischiano in analisi."""
    base = {
        "symbol": "AAA",
        "book_side": "long",
        "held": False,
        "daily": _daily(100.0, 106.0, 99.0, 105.0, 100.0),
        "intraday_bars": _bars_5min([("2026-08-12T14:10:00+00:00", 101.0)]),
        "eligible_cycle_at": "2026-08-12T14:07:00+00:00",
        "size_usd": 2200.0,
        "slot_fraction": 0.02,
        "cutoff": "2026-08-12T20:00:00+00:00",
        "exit_policy": "EOD_close",
        "confidenza": "congetturale",
    }
    apertura = compute_opportunity({**base, "eligible_cycle_source": "session_open"})
    decisione = compute_opportunity(
        {**base, "eligible_cycle_source": "execution_decisions.tick_time"}
    )
    assert apertura["entry"]["eligible_cycle_source"] == "session_open"
    assert decisione["entry"]["eligible_cycle_source"] == "execution_decisions.tick_time"


def test_serie_legacy_affiancata_non_sostituita():
    """La v2 pubblica il numero legacy accanto al proprio, etichettato: il
    ricalcolo del pregresso affianca, non riscrive (#246 Q2)."""
    est = compute_opportunity(
        {
            "symbol": "ORCL",
            "book_side": "long",
            "held": False,
            "daily": _daily(240.0, 246.0, 239.0, 245.0, 232.5),
            "size_usd": 2200.0,
            "slot_fraction": 0.02,
            "cutoff": "2026-08-12T20:00:00+00:00",
            "exit_policy": "EOD_close",
            "confidenza": "congetturale",
        }
    )
    assert est["legacy"]["costo_usd"] == pytest.approx(est["gross_opportunity_usd"])
    assert "close_to_close" in est["legacy"]["formula"]
    assert est["legacy"]["letta_dalla_sintesi_28_09"] is False
    # La v2 resta il numero della sintesi, e non e' il numero legacy.
    assert est["accessible_opportunity_usd"] != est["legacy"]["costo_usd"]
