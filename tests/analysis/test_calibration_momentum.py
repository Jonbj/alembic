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


from src.analysis.calibration.momentum import select_top


def test_seleziona_i_migliori_n():
    scores = {"AAA": 0.5, "BBB": 0.1, "CCC": 0.9, "DDD": -0.2}
    assert select_top(scores, n_top=2) == ("CCC", "AAA")


def test_pareggio_risolto_alfabeticamente_per_determinismo():
    """Due punteggi identici devono dare sempre lo stesso paniere."""
    scores = {"BBB": 0.5, "AAA": 0.5, "CCC": 0.1}
    assert select_top(scores, n_top=2) == ("AAA", "BBB")


def test_n_top_maggiore_del_disponibile_restituisce_tutto():
    scores = {"AAA": 0.5, "BBB": 0.1}
    assert select_top(scores, n_top=10) == ("AAA", "BBB")


def test_punteggi_vuoti_danno_tupla_vuota():
    assert select_top({}, n_top=5) == ()


def test_include_anche_punteggi_negativi_se_sono_i_migliori():
    """Long-only NON significa filtro sul segno: il paniere e' relativo.
    Il filtro assoluto e' un'ipotesi separata, non un default."""
    scores = {"AAA": -0.1, "BBB": -0.5, "CCC": -0.9}
    assert select_top(scores, n_top=2) == ("AAA", "BBB")


from src.analysis.calibration.momentum import equal_weighted_return


def test_rendimento_equipesato():
    closes = {
        "AAA": {0: 100.0, 21: 110.0},   # +10%
        "BBB": {0: 100.0, 21: 90.0},    # -10%
    }
    assert equal_weighted_return(("AAA", "BBB"), closes, 0, 21) == pytest.approx(0.0)


def test_media_dei_rendimenti_non_rendimento_della_media():
    """Equipesato = media aritmetica dei rendimenti dei componenti."""
    closes = {"AAA": {0: 10.0, 21: 20.0}, "BBB": {0: 1000.0, 21: 1100.0}}
    # +100% e +10% -> 55%, NON un rendimento pesato per prezzo
    assert equal_weighted_return(("AAA", "BBB"), closes, 0, 21) == pytest.approx(0.55)


def test_simbolo_senza_prezzi_nel_periodo_e_saltato_non_azzerato():
    """Chi non ha dati esce dal calcolo; NON contribuisce con uno zero."""
    closes = {"AAA": {0: 100.0, 21: 110.0}, "BBB": {0: 100.0}}
    assert equal_weighted_return(("AAA", "BBB"), closes, 0, 21) == pytest.approx(0.10)


def test_nessun_simbolo_valido_da_none():
    closes = {"AAA": {0: 100.0}}
    assert equal_weighted_return(("AAA",), closes, 0, 21) is None


def test_paniere_vuoto_da_none():
    assert equal_weighted_return((), {}, 0, 21) is None
