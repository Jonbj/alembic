"""#169: confronto delle regole di dedup del ranker S4 contro i forward return.

Il ranker S4 usa il segnale piu' recente per ticker (riduzione simbolo-giorno
in `compute_s4_ic.py`): il punteggio che finisce nel ranking dipende da quale
articolo e' arrivato per ultimo, non dal peso complessivo della notizia. La
issue chiede la MISURA, non la decisione: nessuna regola cambia qui, si
confrontano solo le candidate — ultimo (produzione), massimo, media pesata
per confidenza, finestra temporale — contro i forward return gia' calcolati
su `sentiment_signals` dal worker quotidiano.

Questi test inchiodano la parte che decide la validita' del numero:

  1. `ultimo` e' il segnale piu' recente del simbolo-giorno, senza la
     preferenza ensemble del ranker vero — e' la stessa riduzione di
     `compute_s4_ic.py`, e dev'esserlo perche' i due numeri siano
     confrontabili. Il caso INTC della Week 35 (fan-out a 0.000 che
     sovrascrive il +0.228 issuer-specific) e' il test che lo difende;
  2. le regole candidate NON inventano informazione: massimo e' il picco
     del giorno, media_conf/media_decay sono funzioni dei soli score;
  3. l'IC e' Spearman cross-sectional giorno per giorno con le stesse
     guardie di `compute_s4_ic.py` (minimo 5 simboli, serie costante
     scartata), e il t e' calcolato sui giorni, non sulle osservazioni;
  4. il confronto al gate 0.30 (baseline di produzione, NON taratura: qui
     si misura) separa i flip "persi" (la candidata passa dove il ranker
     attuale skippa) dai flip "evitati" (il ranker passa dove la
     candidata non passerebbe).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

from scripts.measure_169_dedup_rules import (
    MEZZA_VITA_ORE,
    RULES,
    SOGLIA_GATE,
    dedup_score,
    media_fwd,
    raggruppa_per_simbolo_giorno,
    riduci_a_simbolo_giorno,
    serie_ic_giornaliera,
    sintesi_ic,
    statistiche_gate,
    varianza_intraday,
)


UTC = timezone.utc


def _sig(
    giorno: date, symbol: str, hour: float, score: float,
    conf: float = 0.8, fallback: bool = False, fwd_1d: float | None = None,
) -> dict:
    """Un segnale come li produce `leggi_segnali` (giorno, orario, score, fwd)."""
    h = int(hour)
    m = round((hour - h) * 60)
    return {
        "giorno": giorno,
        "symbol": symbol,
        "generated_at": datetime(giorno.year, giorno.month, giorno.day, h, m, tzinfo=UTC),
        "score": score,
        "confidence": conf,
        "fallback": fallback,
        "fwd_1d": fwd_1d,
        "fwd_3d": None,
        "fwd_5d": None,
    }


D = date(2026, 8, 27)


# ── Le regole di dedup ────────────────────────────────────────────────────────


def test_le_regole_candidate_sono_esattamente_quelle_della_issue():
    assert set(RULES) == {"ultimo", "massimo", "media_conf", "media_decay"}


def test_ultimo_usa_il_segnale_piu_recente_del_simbolo_giorno():
    gruppo = [_sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037)]
    assert dedup_score(gruppo, "ultimo") == 0.037


def test_ultimo_non_preferisce_lessemble_sul_segnale_giorno():
    # Come compute_s4_ic.py: l'ultima riga del giorno vince anche se e'
    # fallback. Il ranker vero preferisce l'ensemble (fallback ASC prima di
    # generated_at DESC); la riduzione simbolo-giorno e' una approssimazione
    # dichiarata, uguale per entrambe le misure perche' siano confrontabili.
    gruppo = [_sig(D, "INTC", 16.5, 0.228, fallback=False),
              _sig(D, "INTC", 17.0, 0.000, fallback=True)]
    assert dedup_score(gruppo, "ultimo") == 0.000


def test_massimo_prende_il_picco_del_giorno():
    gruppo = [_sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037),
              _sig(D, "MU", 17.0, 0.005)]
    assert dedup_score(gruppo, "massimo") == 0.565


def test_massimo_su_giornata_tutta_negativa_resta_negativo():
    # La regola non inventa positivita': e' il massimo dei voti espressi.
    gruppo = [_sig(D, "TSLA", 14.0, -0.110), _sig(D, "TSLA", 15.0, -0.050)]
    assert dedup_score(gruppo, "massimo") == -0.050


def test_media_conf_pesata_per_confidenza():
    gruppo = [_sig(D, "NOW", 14.0, 0.6, conf=0.2),
              _sig(D, "NOW", 15.0, 0.0, conf=0.8)]
    assert math.isclose(dedup_score(gruppo, "media_conf"), 0.12)


def test_media_conf_con_confidenze_tutte_zero_cade_sulla_media_semplice():
    gruppo = [_sig(D, "NVDA", 14.0, 0.629, conf=0.0),
              _sig(D, "NVDA", 14.25, -0.405, conf=0.0)]
    assert math.isclose(dedup_score(gruppo, "media_conf"), (0.629 - 0.405) / 2)


def test_media_decay_dimezza_il_peso_ogni_mezza_vita():
    # Due segnali distanti MEZZA_VITA_ORE: il piu' vecchio pesa la metà'.
    nuovo = _sig(D, "MU", 20.0, 0.5)
    vecchio = _sig(D, "MU", 20.0 - MEZZA_VITA_ORE, -0.5)
    gruppo = [vecchio, nuovo]
    atteso = (0.5 * 1.0 + (-0.5) * 0.5) / 1.5
    assert math.isclose(dedup_score(gruppo, "media_decay"), atteso)


def test_media_decay_sta_vicino_al_recente_e_non_alla_media_semplice():
    nuovo = _sig(D, "MU", 23.0, 0.5)
    vecchio = _sig(D, "MU", 12.0, -0.5)  # ~2 mezze vite prima: peso ~1/4
    gruppo = [vecchio, nuovo]
    decay = dedup_score(gruppo, "media_decay")
    # media semplice sarebbe 0.0: la finestra tiene la lettura del recente
    assert 0.2 < decay < 0.5


def test_media_decay_su_un_solo_segnale_e_lo_score_di_quel_segnale():
    gruppo = [_sig(D, "MSFT", 16.0, 0.212)]
    for regola in RULES:
        assert dedup_score(gruppo, regola) == 0.212


# ── Riduzione a un'osservazione per simbolo-giorno ───────────────────────────


def test_riduci_mantiene_un_osservazione_per_simbolo_giorno_con_fwd_dellultimo():
    segnali = [
        _sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037, fwd_1d=0.184),
        _sig(D, "NVDA", 14.0, 0.629),
        _sig(date(2026, 8, 26), "MU", 15.0, 0.1),  # altro giorno: altra riga
    ]
    oss = riduci_a_simbolo_giorno(segnali)
    per_chiave = {(o["giorno"], o["symbol"]): o for o in oss}
    mu = per_chiave[(D.isoformat(), "MU")]
    assert mu["n"] == 2
    assert mu["scores"]["ultimo"] == 0.037
    assert mu["scores"]["massimo"] == 0.565
    assert mu["fwd_1d"] == 0.184  # dal segnale scelto dal ranker (l'ultimo)
    assert len(oss) == 3


def test_riduci_registra_range_e_min_per_la_varianza():
    segnali = [_sig(D, "NVDA", 14.15, -0.405), _sig(D, "NVDA", 16.0, 0.629)]
    oss = riduci_a_simbolo_giorno(segnali)
    assert oss[0]["min_score"] == -0.405
    assert oss[0]["max_score"] == 0.629


# ── IC giornaliero: le stesse guardie di compute_s4_ic.py ─────────────────────


def _oss(giorno: date, symbol: str, score: float, fwd: float,
         regole_extra: dict | None = None) -> dict:
    scores = {"ultimo": score, "massimo": score, "media_conf": score,
              "media_decay": score}
    scores.update(regole_extra or {})
    return {
        "giorno": giorno.isoformat(), "symbol": symbol, "n": 1,
        "scores": scores, "min_score": score, "max_score": score,
        "fwd_1d": fwd, "fwd_3d": None, "fwd_5d": None,
    }


def test_serie_ic_monotona_crescente_fa_ic_uno():
    per_giorno = {
        "2026-08-27": [
            _oss(D, "A", 0.1, 0.01), _oss(D, "B", 0.2, 0.02),
            _oss(D, "C", 0.3, 0.03), _oss(D, "E", 0.4, 0.04),
            _oss(D, "F", 0.5, 0.05),
        ]
    }
    serie = serie_ic_giornaliera(per_giorno, "ultimo", 1)
    assert len(serie) == 1
    assert math.isclose(serie[0][1], 1.0)
    assert serie[0][2] == 5


def test_serie_ic_monotona_decrescente_fa_ic_meno_uno():
    per_giorno = {
        "2026-08-27": [
            _oss(D, "A", 0.1, 0.05), _oss(D, "B", 0.2, 0.04),
            _oss(D, "C", 0.3, 0.03), _oss(D, "E", 0.4, 0.02),
            _oss(D, "F", 0.5, 0.01),
        ]
    }
    assert math.isclose(serie_ic_giornaliera(per_giorno, "ultimo", 1)[0][1], -1.0)


def test_serie_ic_salta_i_giorni_con_meno_di_5_simboli():
    per_giorno = {
        "2026-08-26": [_oss(date(2026, 8, 26), "A", 0.1, 0.01),
                       _oss(date(2026, 8, 26), "B", 0.2, 0.02)],
        "2026-08-27": [
            _oss(D, "A", 0.1, 0.01), _oss(D, "B", 0.2, 0.02),
            _oss(D, "C", 0.3, 0.03), _oss(D, "E", 0.4, 0.04),
            _oss(D, "F", 0.5, 0.05),
        ],
    }
    assert [g for g, _, _ in serie_ic_giornaliera(per_giorno, "ultimo", 1)] == ["2026-08-27"]


def test_serie_ic_salta_le_serie_costanti():
    per_giorno = {
        "2026-08-27": [_oss(D, s, 0.3, f) for s, f in
                       zip("ABCDE", (0.01, 0.02, -0.01, 0.03, -0.02))],
    }
    # score costante: Spearman non e' definito, il giorno esce dalla serie
    assert serie_ic_giornaliera(per_giorno, "ultimo", 1) == []
    per_giorno2 = {
        "2026-08-27": [_oss(D, s, 0.1 * i, 0.0) for i, s in enumerate("ABCDE")],
    }
    assert serie_ic_giornaliera(per_giorno2, "ultimo", 1) == []


def test_serie_ic_esclude_le_osservazioni_senza_fwd_dellorizzonte():
    # 6 simboli, uno senza forward return: il giorno resta in serie (6 >= 5
    # prima del filtro), ma l'osservazione senza target esce dal conteggio
    per_giorno = {
        "2026-08-27": [
            _oss(D, "A", 0.1, 0.01), _oss(D, "B", 0.2, 0.02),
            _oss(D, "C", 0.3, 0.03), _oss(D, "E", 0.4, 0.04),
            _oss(D, "F", 0.5, 0.05), _oss(D, "G", 0.6, None),
        ]
    }
    assert serie_ic_giornaliera(per_giorno, "ultimo", 1)[0][2] == 5


def test_serie_ic_confronta_le_regole_sullo_stesso_campione():
    # stesso giorno, regole diverse: la regola che ordina diversamente ha
    # IC diverso — questo e' il cuore del confronto della issue
    per_giorno = {
        "2026-08-27": [
            _oss(D, "A", 0.1, 0.05, {"massimo": 0.5}),
            _oss(D, "B", 0.2, 0.01, {"massimo": 0.1}),
            _oss(D, "C", 0.3, 0.04, {"massimo": 0.4}),
            _oss(D, "E", 0.4, 0.02, {"massimo": 0.2}),
            _oss(D, "F", 0.5, 0.03, {"massimo": 0.3}),
        ]
    }
    ic_ultimo = serie_ic_giornaliera(per_giorno, "ultimo", 1)[0][1]
    ic_massimo = serie_ic_giornaliera(per_giorno, "massimo", 1)[0][1]
    assert ic_ultimo < 0 < ic_massimo


def test_sintesi_ic_calcola_t_statistica_sui_giorni():
    serie = [("2026-08-25", 0.10, 5), ("2026-08-26", 0.30, 6),
             ("2026-08-27", 0.20, 7), ("2026-08-28", 0.40, 5)]
    s = sintesi_ic(serie)
    valori = [0.10, 0.30, 0.20, 0.40]
    media = sum(valori) / 4
    dev = math.sqrt(sum((v - media) ** 2 for v in valori) / 3)
    assert math.isclose(s["ic_medio"], media)
    assert math.isclose(s["dev_std"], dev)
    assert math.isclose(s["t_stat"], media / (dev / math.sqrt(4)))


def test_sintesi_ic_con_meno_di_3_giorni_non_da_numero():
    assert sintesi_ic([("g", 0.1, 5), ("g2", 0.2, 5)])["ic_medio"] is None
    assert sintesi_ic([])["ic_medio"] is None


# ── Il gate 0.30 e i flip contro la regola di produzione ─────────────────────


def test_statistiche_gate_conteggia_pass_e_flip_persi():
    # 4 simbolo-giorni. MU: il ranker attuale skippa a 0.005 mentre il picco
    # del giorno (0.565) passava — il caso della issue, flip perso. NOW: il
    # massimo del giorno e' 0.1425, sotto gate anche lui: nessun flip, il
    # caso e' scoperto da entrambe le regole (come nel rapporto 08-27, dove
    # il +0.1425 sovrascritto restava comunque sotto la soglia). AAPL:
    # passano entrambe, nessun flip. TSLA: non passa nessuna.
    oss = [
        _oss(D, "MU", 0.005, 0.184, {"massimo": 0.565}),
        _oss(D, "NOW", 0.021, 0.100, {"massimo": 0.1425}),
        _oss(D, "AAPL", 0.4, 0.001, {"massimo": 0.45}),
        _oss(D, "TSLA", 0.1, -0.02, {"massimo": 0.008}),
    ]
    st = statistiche_gate(oss)
    assert st["massimo"]["n_sopra_soglia"] == 2  # MU e AAPL
    assert st["ultimo"]["n_sopra_soglia"] == 1  # AAPL
    assert st["massimo"]["n_flip_persi"] == 1  # solo MU
    assert math.isclose(st["massimo"]["media_fwd_1d_flip_persi"], 0.184)
    assert st["massimo"]["n_flip_evitati"] == 0


def test_statistiche_gate_conteggia_i_flip_evitati():
    oss = [
        _oss(D, "GE", 0.4, -0.05, {"massimo": 0.05}),
        _oss(D, "DELL", 0.35, -0.03, {"massimo": 0.02}),
    ]
    st = statistiche_gate(oss)
    assert st["ultimo"]["n_sopra_soglia"] == 2
    assert st["massimo"]["n_sopra_soglia"] == 0
    assert st["massimo"]["n_flip_evitati"] == 2
    assert math.isclose(st["massimo"]["media_fwd_1d_flip_evitati"], -0.04)
    assert st["massimo"]["n_flip_persi"] == 0


def test_soglia_gate_default_e_quella_di_produzione():
    assert SOGLIA_GATE == 0.30


def test_media_fwd_su_lista_vuota_e_none():
    assert media_fwd([]) is None


# ── Varianza intraday: il contesto che motiva la issue ───────────────────────


def test_varianza_intraday_aggrega_range_e_multiolicita():
    oss = [
        # NVDA: 2 segnali, range 1.034 (il caso della issue)
        _oss(D, "NVDA", 0.629, 0.01, {}),
        # MU: 1 segnale, range 0
        _oss(D, "MU", 0.037, 0.02, {}),
        # MS: 1 segnale
        _oss(D, "MS", 0.2, 0.03, {}),
    ]
    oss[0]["n"] = 2
    oss[0]["min_score"] = -0.405
    oss[1]["n"] = 1
    oss[2]["n"] = 1
    v = varianza_intraday(oss)
    assert v["simbolo_giorni"] == 3
    assert v["con_piu_segnali"] == 1
    assert v["quota_con_piu_segnali"] == 1 / 3
    assert math.isclose(v["range_mediano"], 1.034)
    assert math.isclose(v["range_massimo"], 1.034)


def test_varianza_intraday_con_una_sola_osservazione_multi_segnale():
    oss = [_oss(D, "MU", 0.037, 0.02, {})]
    oss[0]["n"] = 20
    oss[0]["min_score"] = -0.200
    oss[0]["max_score"] = 0.565
    v = varianza_intraday(oss)
    assert v["simbolo_giorni"] == 1
    assert v["con_piu_segnali"] == 1
    assert v["quota_con_piu_segnali"] == 1.0
    assert math.isclose(v["range_mediano"], 0.765)


def test_raggruppa_separa_per_giorno_e_simbolo():
    segnali = [
        _sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037),
        _sig(date(2026, 8, 26), "MU", 15.0, 0.1),
    ]
    gruppi = raggruppa_per_simbolo_giorno(segnali)
    assert set(gruppi) == {(D, "MU"), (date(2026, 8, 26), "MU")}
    assert len(gruppi[(D, "MU")]) == 2