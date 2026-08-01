"""Motore di calibrazione: segnale, selezione, rendimenti, statistiche."""
import pytest

from src.analysis.calibration.momentum import momentum_scores


def test_momentum_e_il_rendimento_fra_due_posizioni():
    """12-2: dal giorno idx-skip-lookback al giorno idx-skip."""
    closes = {"AAA": {i: 100.0 for i in range(300)}}
    closes["AAA"][10] = 100.0   # inizio finestra: 273 - 21 - 242 = 10
    closes["AAA"][252] = 150.0  # fine finestra: 273 - 21 = 252
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert out["AAA"] == pytest.approx(0.50)


def test_skip_esclude_il_periodo_recente():
    """Il movimento DOPO idx-skip non deve entrare nel punteggio."""
    closes = {"AAA": {i: 100.0 for i in range(300)}}
    closes["AAA"][10] = 100.0
    closes["AAA"][252] = 150.0
    closes["AAA"][273] = 10.0   # crollo recente: dentro lo skip, va ignorato
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert out["AAA"] == pytest.approx(0.50)


def test_simbolo_con_storia_insufficiente_e_escluso():
    """Niente punteggio inventato per chi non ha abbastanza storia."""
    closes = {
        "AAA": {i: 100.0 for i in range(300)},
        "BBB": {i: 100.0 for i in range(260, 300)},  # troppo corto
    }
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert "AAA" in out
    assert "BBB" not in out


def test_prezzo_iniziale_nullo_o_assente_esclude_il_simbolo():
    closes = {
        "AAA": {i: 100.0 for i in range(300)},
        "BBB": {i: 100.0 for i in range(300)},
        "CCC": {i: 100.0 for i in range(300)},
    }
    closes["BBB"][10] = 0.0     # divisione per zero
    del closes["CCC"][252]      # buco nella serie
    out = momentum_scores(closes, idx=273, lookback=242, skip=21)
    assert set(out) == {"AAA"}


def test_indice_troppo_piccolo_da_dizionario_vuoto():
    """Se la finestra andrebbe prima dell'inizio della serie, nessun punteggio."""
    closes = {"AAA": {i: 100.0 for i in range(300)}}
    assert momentum_scores(closes, idx=100, lookback=242, skip=21) == {}
