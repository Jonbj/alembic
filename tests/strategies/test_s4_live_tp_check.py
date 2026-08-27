"""Obbligazione Q7 del contratto: quanti P0 sarebbe stati toccati dal TP live.

Il TP live e' acceso di default ma solo sui submit **non frazionabili**, mentre
il contratto congela P0 con `take_profit.enabled: false`. Se la divergenza
tocca piu' del 5% degli intenti, P0 non e' piu' il benchmark operativo reale e
la definizione va corretta prima di n=0.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.strategies.s4.live_tp_check import (
    LiveTpSettings,
    P0Lifecycle,
    PricePath,
    assess_live_tp_exposure,
    load_live_tp_settings,
)

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "s4_exit_trial.yaml"
ENTRY = datetime(2026, 8, 25, 15, 7, tzinfo=UTC)
EXIT = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)
SETTINGS = LiveTpSettings(
    take_profit_pct=0.06,
    bracket_enabled=True,
    threshold_pct_of_intents=5.0,
    perimeter="whole_share_non_fractionable",
)


def _lifecycle(index: int, **overrides) -> P0Lifecycle:
    values = {
        "intent_id": f"intent-{index}",
        "symbol": "AMD",
        "d0": date(2026, 8, 25),
        "entry_price": 100.0,
        "entry_at": ENTRY,
        "exit_at": EXIT,
        "fractionable": False,
        "comparable": True,
    }
    values.update(overrides)
    return P0Lifecycle(**values)


def _path(high: float | None, **overrides) -> PricePath:
    values = {"highest_high": high, "observed_from": ENTRY, "observed_to": EXIT}
    values.update(overrides)
    return PricePath(**values)


# ── Il perimetro: solo i non frazionabili portano un bracket ───────────────


def test_un_simbolo_frazionabile_non_riceve_il_bracket_e_resta_fuori():
    """Alpaca rifiuta il bracket sugli ordini frazionari: la' il TP non esiste."""
    report = assess_live_tp_exposure(
        [_lifecycle(0, fractionable=True)],
        {"intent-0": _path(200.0)},
        SETTINGS,
    )

    assert report["in_perimeter"] == 0
    assert report["touched"] == 0
    assert report["rows"][0]["outcome"] == "OUT_OF_PERIMETER"


def test_un_non_frazionabile_che_tocca_il_tp_e_contato():
    report = assess_live_tp_exposure(
        [_lifecycle(0)], {"intent-0": _path(106.0)}, SETTINGS
    )

    assert report["in_perimeter"] == 1
    assert report["touched"] == 1
    assert report["rows"][0]["take_profit_price"] == pytest.approx(106.0)


def test_il_confronto_e_inclusivo_sul_prezzo_limite():
    """Un limit a 106.00 con massimo 106.00 e' eseguibile: contarlo escluso
    sottostimerebbe l'esposizione, che e' la direzione sbagliata per un gate."""
    sopra = assess_live_tp_exposure([_lifecycle(0)], {"intent-0": _path(106.0)}, SETTINGS)
    sotto = assess_live_tp_exposure(
        [_lifecycle(0)], {"intent-0": _path(105.99)}, SETTINGS
    )

    assert sopra["touched"] == 1
    assert sotto["touched"] == 0


def test_il_prezzo_di_trigger_usa_l_arrotondamento_del_codice_live():
    """`round(price * (1 + pct), 2)`: un tick di differenza cambia il verdetto."""
    report = assess_live_tp_exposure(
        [_lifecycle(0, entry_price=33.33)], {"intent-0": _path(35.33)}, SETTINGS
    )

    # 33.33 × 1.06 = 35.3298 -> 35.33
    assert report["rows"][0]["take_profit_price"] == pytest.approx(35.33)
    assert report["touched"] == 1


# ── La soglia del 5% e cosa implica ────────────────────────────────────────


def test_sotto_soglia_p0_resta_il_benchmark():
    lifecycles = [_lifecycle(i) for i in range(40)]
    paths = {f"intent-{i}": _path(101.0) for i in range(40)}
    paths["intent-0"] = _path(110.0)

    report = assess_live_tp_exposure(lifecycles, paths, SETTINGS)

    assert report["touched"] == 1
    assert report["touched_pct_of_intents"] == pytest.approx(2.5)
    assert report["exceeds_threshold"] is False
    assert report["p0_remains_benchmark"] is True


def test_sopra_soglia_p0_va_ridefinito_prima_di_n0():
    lifecycles = [_lifecycle(i) for i in range(10)]
    paths = {f"intent-{i}": _path(110.0 if i < 2 else 101.0) for i in range(10)}

    report = assess_live_tp_exposure(lifecycles, paths, SETTINGS)

    assert report["touched_pct_of_intents"] == pytest.approx(20.0)
    assert report["exceeds_threshold"] is True
    assert report["p0_remains_benchmark"] is False


def test_la_percentuale_ha_come_denominatore_tutti_gli_intenti():
    """Il contratto dice `% degli intenti`, non `% dei non frazionabili`.

    Usare il perimetro come denominatore gonfierebbe la percentuale e farebbe
    scattare una ridefinizione di P0 che il contratto non chiede.
    """
    lifecycles = [
        _lifecycle(0),
        _lifecycle(1, fractionable=True),
        _lifecycle(2, fractionable=True),
        _lifecycle(3, fractionable=True),
    ]
    paths = {"intent-0": _path(110.0)}

    report = assess_live_tp_exposure(lifecycles, paths, SETTINGS)

    assert report["intents"] == 4
    assert report["in_perimeter"] == 1
    assert report["touched"] == 1
    assert report["touched_pct_of_intents"] == pytest.approx(25.0)
    assert report["denominator"] == "all_intents"


# ── Dati mancanti: ignoto non e' zero ──────────────────────────────────────


def test_un_path_mancante_e_ignoto_non_un_non_tocco():
    """Contarlo come non toccato sottostimerebbe proprio cio' che il gate cerca."""
    report = assess_live_tp_exposure([_lifecycle(0)], {}, SETTINGS)

    assert report["touched"] == 0
    assert report["unknown"] == 1
    assert report["rows"][0]["outcome"] == "PRICE_PATH_MISSING"
    assert report["conclusive"] is False


def test_una_fractionability_ignota_non_si_indovina():
    report = assess_live_tp_exposure(
        [_lifecycle(0, fractionable=None)], {"intent-0": _path(110.0)}, SETTINGS
    )

    assert report["unknown"] == 1
    assert report["rows"][0]["outcome"] == "FRACTIONABILITY_UNKNOWN"
    assert report["conclusive"] is False


def test_un_prezzo_di_ingresso_assente_non_produce_un_trigger_a_zero():
    report = assess_live_tp_exposure(
        [_lifecycle(0, entry_price=0.0)], {"intent-0": _path(110.0)}, SETTINGS
    )

    assert report["unknown"] == 1
    assert report["rows"][0]["outcome"] == "ENTRY_PRICE_MISSING"


def test_con_ignoti_il_verdetto_resta_non_conclusivo_anche_sotto_soglia():
    """Un ignoto puo' ribaltare il gate: dichiararlo sotto soglia sarebbe falso."""
    lifecycles = [_lifecycle(i) for i in range(20)]
    paths = {f"intent-{i}": _path(101.0) for i in range(19)}

    report = assess_live_tp_exposure(lifecycles, paths, SETTINGS)

    assert report["touched"] == 0
    assert report["unknown"] == 1
    assert report["exceeds_threshold"] is False
    assert report["conclusive"] is False
    assert report["worst_case_pct_of_intents"] == pytest.approx(5.0)


def test_il_caso_peggiore_conta_gli_ignoti_come_tocchi():
    lifecycles = [_lifecycle(i) for i in range(10)]
    paths = {f"intent-{i}": _path(101.0) for i in range(8)}

    report = assess_live_tp_exposure(lifecycles, paths, SETTINGS)

    assert report["touched_pct_of_intents"] == pytest.approx(0.0)
    assert report["worst_case_pct_of_intents"] == pytest.approx(20.0)
    assert report["worst_case_exceeds_threshold"] is True


# ── Il bracket spento cambia tutto ─────────────────────────────────────────


def test_col_bracket_spento_nessun_intento_e_in_perimetro():
    settings = LiveTpSettings(
        take_profit_pct=0.06,
        bracket_enabled=False,
        threshold_pct_of_intents=5.0,
        perimeter="whole_share_non_fractionable",
    )

    report = assess_live_tp_exposure(
        [_lifecycle(0)], {"intent-0": _path(200.0)}, settings
    )

    assert report["in_perimeter"] == 0
    assert report["touched"] == 0
    assert report["bracket_enabled"] is False


# ── I parametri vengono dal contratto e dalla config live ──────────────────


def test_le_impostazioni_arrivano_dal_contratto():
    settings = load_live_tp_settings(CONTRACT_PATH)

    assert settings.threshold_pct_of_intents == 5.0
    assert settings.perimeter == "whole_share_non_fractionable"
    assert settings.take_profit_pct == pytest.approx(0.06)


def test_un_contratto_che_accendesse_il_tp_nel_trial_e_rifiutato(tmp_path):
    """Se P0 avesse il TP, la domanda di Q7 non avrebbe senso."""
    import yaml

    payload = yaml.safe_load(CONTRACT_PATH.read_bytes())
    payload["risk_overlay"]["take_profit"]["enabled"] = True
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="take_profit"):
        load_live_tp_settings(path)


def test_una_finestra_di_prezzo_che_non_copre_la_vita_dell_intento_e_ignota():
    report = assess_live_tp_exposure(
        [_lifecycle(0)],
        {"intent-0": _path(101.0, observed_to=EXIT - timedelta(days=1))},
        SETTINGS,
    )

    assert report["unknown"] == 1
    assert report["rows"][0]["outcome"] == "PRICE_PATH_INCOMPLETE"


# ── Il perimetro d'universo: evidenza piu' forte del campione ──────────────


def test_un_universo_tutto_frazionabile_rende_il_perimetro_vuoto():
    """Se nessun candidato puo' ricevere un bracket, la divergenza non esiste."""
    from src.strategies.s4.live_tp_check import assess_universe_perimeter

    report = assess_universe_perimeter(
        {"META": True, "NVDA": True, "CSCO": True}, SETTINGS
    )

    assert report["universe"] == 3
    assert report["non_fractionable"] == 0
    assert report["non_fractionable_pct"] == pytest.approx(0.0)
    assert report["perimeter_structurally_empty"] is True


def test_un_solo_candidato_non_frazionabile_riapre_il_perimetro():
    from src.strategies.s4.live_tp_check import assess_universe_perimeter

    report = assess_universe_perimeter(
        {"META": True, "NVDA": True, "BRK.A": False}, SETTINGS
    )

    assert report["non_fractionable"] == 1
    assert report["perimeter_structurally_empty"] is False
    assert report["non_fractionable_symbols"] == ["BRK.A"]


def test_una_fractionability_ignota_non_svuota_il_perimetro():
    """Un simbolo di cui non sappiamo nulla non e' un simbolo frazionabile."""
    from src.strategies.s4.live_tp_check import assess_universe_perimeter

    report = assess_universe_perimeter({"META": True, "IGNOTO": None}, SETTINGS)

    assert report["unknown"] == 1
    assert report["perimeter_structurally_empty"] is False


def test_col_bracket_spento_il_perimetro_e_vuoto_comunque():
    from src.strategies.s4.live_tp_check import assess_universe_perimeter

    settings = LiveTpSettings(
        take_profit_pct=0.06,
        bracket_enabled=False,
        threshold_pct_of_intents=5.0,
        perimeter="whole_share_non_fractionable",
    )

    report = assess_universe_perimeter({"BRK.A": False}, settings)

    assert report["perimeter_structurally_empty"] is True
    assert report["reason"] == "bracket_disabled"


def test_un_universo_vuoto_non_e_una_prova():
    from src.strategies.s4.live_tp_check import assess_universe_perimeter

    report = assess_universe_perimeter({}, SETTINGS)

    assert report["perimeter_structurally_empty"] is False
    assert report["reason"] == "empty_universe"
