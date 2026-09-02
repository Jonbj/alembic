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
    BASELINE,
    MEZZA_VITA_ORE,
    RULES,
    SOGLIA_GATE,
    analizza_uscite_sotto_soglia,
    costruisci_eventi_uscita,
    dedup_score,
    scelta_produzione,
    media_fwd,
    misura,
    raggruppa_per_simbolo_giorno,
    riduci_a_simbolo_giorno,
    serie_ic_giornaliera,
    sintesi_ic,
    statistiche_gate,
    riepilogo_leggibile,
    riepilogo_uscite_leggibile,
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
    assert set(RULES) == {"ultimo_prod", "ultimo", "massimo", "media_conf", "media_decay"}


def test_la_baseline_e_la_regola_del_ranker_di_produzione():
    # I flip si contano contro cio' che il ranker fa DAVVERO, non contro
    # l'approssimazione di compute_s4_ic.py: altrimenti il conteggio dei
    # flip include casi che in produzione non sarebbero mai avvenuti.
    assert BASELINE == "ultimo_prod"
    assert BASELINE in RULES


def test_ultimo_usa_il_segnale_piu_recente_del_simbolo_giorno():
    gruppo = [_sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037)]
    assert dedup_score(gruppo, "ultimo") == 0.037


def test_ultimo_non_preferisce_lessemble_sul_segnale_giorno():
    # `ultimo` e' la riduzione di compute_s4_ic.py: l'ultima riga del giorno
    # vince anche se e' fallback. NON e' il ranker — resta misurata solo per
    # quantificare lo scarto da `ultimo_prod`.
    gruppo = [_sig(D, "INTC", 16.5, 0.228, fallback=False),
              _sig(D, "INTC", 17.0, 0.000, fallback=True)]
    assert dedup_score(gruppo, "ultimo") == 0.000


# ── `ultimo_prod`: l'ordinamento vero di _FETCH_SIGNALS_FOR_CYCLE ────────────


def test_ultimo_prod_preferisce_lensemble_al_fallback_piu_recente():
    # `ORDER BY symbol, fallback_used ASC, generated_at DESC`: un fallback
    # FinBERT arrivato DOPO non sovrascrive un ensemble. E' il caso che la
    # review ha segnalato: contando i flip contro `ultimo` finivano nel
    # conteggio sovrascritture che in produzione non avvengono.
    gruppo = [_sig(D, "INTC", 16.5, 0.228, fallback=False),
              _sig(D, "INTC", 17.0, 0.000, fallback=True)]
    assert dedup_score(gruppo, "ultimo_prod") == 0.228


def test_ultimo_prod_a_parita_di_stato_prende_il_piu_recente():
    gruppo = [_sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037)]
    assert dedup_score(gruppo, "ultimo_prod") == 0.037


def test_ultimo_prod_su_giornata_tutta_fallback_prende_il_piu_recente():
    # Se non esiste alcun ensemble, la preferenza non ha nulla da preferire:
    # vince la recenza, esattamente come in SQL.
    gruppo = [_sig(D, "MU", 15.0, 0.500, fallback=True),
              _sig(D, "MU", 16.0, 0.020, fallback=True)]
    assert dedup_score(gruppo, "ultimo_prod") == 0.020


def test_ultimo_prod_fra_piu_ensemble_ignora_i_fallback_interposti():
    gruppo = [_sig(D, "MU", 14.0, 0.100, fallback=False),
              _sig(D, "MU", 15.0, 0.900, fallback=True),
              _sig(D, "MU", 16.0, 0.300, fallback=False),
              _sig(D, "MU", 17.0, 0.800, fallback=True)]
    assert dedup_score(gruppo, "ultimo_prod") == 0.300


def test_scelta_produzione_restituisce_il_segnale_non_solo_lo_score():
    ensemble = _sig(D, "INTC", 16.5, 0.228, fallback=False, fwd_1d=0.05)
    gruppo = [ensemble, _sig(D, "INTC", 17.0, 0.000, fallback=True, fwd_1d=-0.02)]
    assert scelta_produzione(gruppo) is ensemble


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
    assert mu["fwd_1d"] == 0.184  # dal segnale scelto dal ranker
    assert len(oss) == 3


def test_riduci_prende_il_fwd_del_segnale_scelto_dal_ranker_non_dellultimo():
    # Il target deve essere il futuro del segnale su cui la decisione sarebbe
    # stata presa. Con un fallback FinBERT che chiude la giornata, quel
    # segnale e' l'ensemble precedente, non l'ultima riga per orario.
    segnali = [
        _sig(D, "INTC", 16.5, 0.228, fallback=False, fwd_1d=0.05),
        _sig(D, "INTC", 17.0, 0.000, fallback=True, fwd_1d=-0.02),
    ]
    oss = riduci_a_simbolo_giorno(segnali)
    assert oss[0]["fwd_1d"] == 0.05
    assert oss[0]["scores"]["ultimo_prod"] == 0.228
    assert oss[0]["scores"]["ultimo"] == 0.000
    assert oss[0]["ensemble_prod"] is True
    assert oss[0]["ensemble_ultimo"] is False


def test_riduci_registra_range_e_min_per_la_varianza():
    segnali = [_sig(D, "NVDA", 14.15, -0.405), _sig(D, "NVDA", 16.0, 0.629)]
    oss = riduci_a_simbolo_giorno(segnali)
    assert oss[0]["min_score"] == -0.405
    assert oss[0]["max_score"] == 0.629


# ── IC giornaliero: le stesse guardie di compute_s4_ic.py ─────────────────────


def _oss(giorno: date, symbol: str, score: float, fwd: float,
         regole_extra: dict | None = None) -> dict:
    scores = {"ultimo_prod": score, "ultimo": score, "massimo": score,
              "media_conf": score, "media_decay": score}
    scores.update(regole_extra or {})
    return {
        "giorno": giorno.isoformat(), "symbol": symbol, "n": 1,
        "scores": scores, "min_score": score, "max_score": score,
        "ensemble_prod": True,  # un solo segnale: non fallback
        "ensemble_ultimo": True,
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


def test_statistiche_gate_conta_i_flip_contro_ultimo_prod_non_contro_ultimo():
    """Il rilievo della review, come test.

    INTC: un fallback FinBERT a 0.00 chiude la giornata dopo un ensemble a
    0.40. `ultimo` (ultimo per orario) vede 0.00 e crede che il ranker skippi
    il titolo; il ranker vero (`ultimo_prod`) usa l'ensemble a 0.40 e il
    titolo passa. Contando i flip contro `ultimo`, `massimo` risulterebbe
    "recuperare" un ingresso che in produzione non era mai stato perso.
    """
    oss = [
        _oss(D, "INTC", 0.00, 0.03,
             {"ultimo_prod": 0.40, "massimo": 0.55}),
        _oss(D, "TSLA", 0.10, -0.02, {"ultimo_prod": 0.10, "massimo": 0.60}),
    ]
    st = statistiche_gate(oss)
    # INTC passa gia' con il ranker vero: non e' un flip perso.
    assert st["massimo"]["n_flip_persi"] == 1  # solo TSLA
    assert math.isclose(st["massimo"]["media_fwd_1d_flip_persi"], -0.02)
    # `ultimo` sotto soglia su INTC dove il ranker vero passa: e' `ultimo`
    # (non il ranker) a "perdere" l'ingresso — lo scarto dell'approssimazione.
    assert st["ultimo"]["n_flip_evitati"] == 1
    assert st["ultimo_prod"]["n_flip_persi"] == 0
    assert st["ultimo_prod"]["n_flip_evitati"] == 0


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


# ── Casi limite del --since: i due TypeError della review #460 ────────────────


def test_misura_e_riepilogo_finestra_recente_senza_fwd_non_crashano():
    # Finestra recente (--since a pochi giorni dal run): segnali ci sono ma il
    # worker quotidiano non ha ancora scritto i forward return. media_fwd
    # restituisce None sul campione vuoto e il riepilogo non deve esplodere —
    # era il primo TypeError della review (formattare None come float sul
    # campo media_fwd_1d_campione).
    segnali = [
        _sig(D, "MU", 15.0, 0.565), _sig(D, "MU", 16.0, 0.037),  # n=2
        _sig(D, "NVDA", 14.0, 0.629),
    ]
    osservazioni = riduci_a_simbolo_giorno(segnali)
    assert all(o["fwd_1d"] is None for o in osservazioni)

    risultato = misura(osservazioni, since="2026-08-28")
    gate = risultato["gate_0.30"]["tutti"]
    assert gate["n_campione"] == 0
    assert gate["media_fwd_1d_campione"] is None
    assert "media incondizionata n/d" in riepilogo_leggibile(risultato)


def test_misura_e_riepilogo_senza_simbolo_giorni_multi_segnale_non_crashano():
    # Neanche un simbolo-giorno con piu' di un segnale: il range intraday non
    # e' definito (varianza_intraday restituisce None) e il riepilogo non deve
    # esplodere — il secondo TypeError della review sui campi range_mediano/
    # range_massimo.
    osservazioni = [
        _oss(D, "MU", 0.037, 0.02),
        _oss(D, "NVDA", 0.629, 0.01),
    ]
    risultato = misura(osservazioni, since="2026-06-15")
    v = risultato["varianza_intraday"]
    assert v["simbolo_giorni"] == 2
    assert v["con_piu_segnali"] == 0
    assert v["range_mediano"] is None and v["range_massimo"] is None
    assert "range (max-min) mediano n/d (max n/d)" in riepilogo_leggibile(risultato)


# ── Uscite l'via below_entry_gate (#169 follow-up 2026-09-01) ─────────────────
#
# La misura del corpo della issue era sugli (vince/salta al gate 0.30).
# L'evidenza del 2026-09-01 (HOOD whipsaw: +0,4815 → +0,0228 → SELL a 105 min)
# ha aggiunto un costo che l'ingresso-gate non vedeva: la sostituzione di un
# segnale forte chiude POSIZIONI APERTE via `below_entry_gate`. Questi test
# misurano l'uscita, sullo stesso campione di regole e la stessa soglia di
# produzione. Il ranker non cambia, nessun parametro cambia: è misura.


def _evento_uscita(
    decision_at: datetime, symbol: str, segnali: list[dict],
    realized: float,
) -> dict:
    """Una chiusura S4 con exit_mechanism=below_entry_gate.

    `segnali` sono tutti i segnali del simbolo con generated_at <= decision_at
    nello stesso giorno (la finestra di freschezza del ranker è hours=4, ma
    l'analisi usa l'intero storico del giorno per non nascondere il caso HOOD,
    in cui il segnale forte era di soli 14 min prima).
    """
    return {
        "decision_at": decision_at,
        "symbol": symbol,
        "segnali": segnali,
        "net_pnl": realized,
    }


def test_costruisci_eventi_uscita_isola_segnali_strettamente_precedenti():
    """Al tick di uscita si guardano i segnali GENERATI prima o uguale.

    Il caso HOOD: +0.4815 a 10:47, decision tick 12:37 — il segnale forte è
    105 minuti prima. Un filtro > decision_at lo escluderebbe per costruzione
    e maschererebbe proprio il caso che vogliamo misurare.
    """
    segnali = [
        _sig(D, "HOOD", 10.78, 0.4815),      # 10:47
        _sig(D, "HOOD", 11.02, 0.0228),      # 11:01 — sovrascrive
        _sig(D, "HOOD", 13.50, -0.10),       # 13:30 — DOPO l'uscita, fuori
    ]
    decision_at = datetime(2026, 8, 27, 12, 37, tzinfo=UTC)
    eventi = costruisci_eventi_uscita(
        [{"decision_at": decision_at, "symbol": "HOOD", "segnali": segnali}]
    )
    assert len(eventi) == 1
    orari = [s["generated_at"].strftime("%H:%M") for s in eventi[0]["segnali"]]
    assert orari == ["10:47", "11:01"]


def test_analizza_uscite_baseline_e_unflip_per_regola_come_negli_ingressi():
    """L'analisi delle uscite usa la stessa baseline e le stesse regole.

    Coerenza: la baseline è la stessa degli ingressi (`ultimo_prod`); le
    regole sono le stesse (issue la stessa); cambia solo il campione (le
    chiusure `below_entry_gate` invece dei simbolo-giorni totali).

    Il test data ha entrambi i segnali come ensemble (per consentire a
    `ultimo_prod` di leggere il piu' recente, 0.10, sotto soglia — esattamente
    la condizione che ha fatto scattare l'uscita via below_entry_gate).
    """
    decision_at = datetime(2026, 8, 27, 12, 37, tzinfo=UTC)
    eventi = [
        _evento_uscita(decision_at, "X", [
            _sig(D, "X", 10.0, 0.40),  # ensemble
            _sig(D, "X", 11.0, 0.10),  # ensemble piu' recente, sotto soglia
        ], realized=-23.06),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    assert set(risultato["regole"].keys()) == set(RULES)
    # `ultimo_prod` è la baseline: per costruzione ha lo stesso score letto
    # dal ranker vero al tick di decisione (0.10 < 0.30). Non salva l'uscita.
    assert risultato["regole"][BASELINE]["n_uscite"] == 1
    assert risultato["regole"][BASELINE]["n_uscite_salve"] == 0


def test_analizza_uscite_massimo_salva_le_posizioni_con_picco_sopra_soglia():
    """HOOD 2026-09-01: il picco ensemble (+0,4815) passava il gate 0,30.

    Sotto `massimo` la posizione NON sarebbe uscita per `below_entry_gate`:
    è il flip "salvato" lato uscita, simmetrico al flip "perso" lato ingresso
    (la candidata passa dove la baseline skippa).

    Entrambi i segnali sono ensemble (lo dice l'evidenza 2026-09-01: il
    10:47 era l' upgrade Morgan Stanley, il 11:02 era un articolo sul meme
    coin BONER — entrambi passati dal resolver, entrambi ensemble, ma a
    confidence molto diversa). Il ranker VEDe entrambi come non-fallback,
    quindi `ultimo_prod` sceglie il piu' recente (0.0228) per la regola
    ensemble-pari-tie-recenza. L'uscita e' scattata per quello.
    """
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    eventi = [
        _evento_uscita(decision_at, "HOOD", [
            _sig(date(2026, 9, 1), "HOOD", 10.78, 0.4815, conf=0.70),
            _sig(date(2026, 9, 1), "HOOD", 11.02, 0.0228, conf=0.25),
        ], realized=-23.06),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    # massimo = +0.4815 >= 0.30: l'uscita NON scatta sotto questa regola
    assert risultato["regole"]["massimo"]["n_uscite_salve"] == 1
    assert math.isclose(risultato["regole"]["massimo"]["realized_uscite_salve"], -23.06)
    # La baseline (`ultimo_prod`) per costruzione ha lo stesso score del
    # segnale scelto dal ranker vero: anche lei legge 0.0228, anche lei ha
    # fatto scattare l'uscita. Per costruzione n_salve = 0 su `ultimo_prod`.
    assert risultato["regole"]["ultimo_prod"]["n_uscite_salve"] == 0


def test_analizza_uscite_nessun_segnale_disponibile_non_salva_niente():
    """Una chiusura senza segnali precedenti è un caso patologico.

    Se manca il campione (segnali vuoto o tutti successivi al decision_at),
    nessuna regola può produrre uno score: l'uscita resta "non salvata" da
    tutte, e il caso va contato ma non contribuisce al realized medio delle
    salvate.
    """
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    eventi = [
        _evento_uscita(decision_at, "EMPTY", [], realized=-10.0),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    assert risultato["regole"]["massimo"]["n_uscite"] == 1
    assert risultato["regole"]["massimo"]["n_uscite_salve"] == 0
    assert risultato["regole"]["massimo"]["realized_uscite_salve"] is None


def test_analizza_uscite_conta_salvi_e_non_salvi_sullo_stesso_campione():
    """Per ogni evento del campione (chiusura below_entry_gate), la candidata
    o legge uno score >= soglia (salva) oppure < soglia (non salva). Le due
    categorie partizionano il campione per ogni regola, con la baseline che
    ha n_salve = 0 per costruzione.

    Una uscita "salvata" dalla candidata = costo evitato. Una uscita "non
    salvata" = costo subito come nel ranker attuale. La somma dei realized
    condizionati pesati per le frequenze da' il realized totale sotto la
    regola candidata: confrontato col realized totale del ranker attuale dice
    se la candidata, sulla finestra, avrebbe migliorato il P&L realized delle
    chiusure below_entry_gate.
    """
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    # A: picco 0.40, massimo salva (>= 0.30). B: entrambi i segnali sotto
    # soglia (massimo 0.20 < 0.30), massimo NON salva.
    eventi = [
        _evento_uscita(decision_at, "A", [
            _sig(date(2026, 9, 1), "A", 10.0, 0.40),
            _sig(date(2026, 9, 1), "A", 11.0, 0.10),
        ], realized=-5.0),
        _evento_uscita(decision_at, "B", [
            _sig(date(2026, 9, 1), "B", 10.0, 0.20),
            _sig(date(2026, 9, 1), "B", 11.0, 0.05),
        ], realized=-3.0),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    m = risultato["regole"]["massimo"]
    assert m["n_uscite"] == 2
    assert m["n_uscite_salve"] == 1  # solo A
    assert math.isclose(m["realized_uscite_salve"], -5.0)


def test_analizza_uscite_realized_salve_e_media_campione():
    """Coerenza di aggregazione: il realized medio del campione e' la media
    pesata per frequenza del realized_salve e del realized_non_salve.

    Una candidata "non salva" niente: il realized della candidata e' il
    realized_medio_uscite del campione (identico al ranker attuale, per
    costruzione). Una candidata che salva k uscite ha realized =
    (somma_salve + somma_non_salve) / N, dove somma_non_salve e' la
    realizzazione del ranker sulle restanti N − k. La differenza
    realized_candidata − realized_attuale dice il valore aggiunto della regola.
    """
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    eventi = [
        _evento_uscita(decision_at, "A", [
            _sig(date(2026, 9, 1), "A", 10.0, 0.40),
            _sig(date(2026, 9, 1), "A", 11.0, 0.10),
        ], realized=-5.0),
        _evento_uscita(decision_at, "B", [
            _sig(date(2026, 9, 1), "B", 10.0, 0.10),
            _sig(date(2026, 9, 1), "B", 11.0, 0.05),
        ], realized=-3.0),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    # media del campione: (-5 + -3) / 2 = -4
    assert math.isclose(risultato["realized_medio_uscite"], -4.0)
    # massimo salva A (picco 0.40 >= 0.30): realized_salve = -5
    assert math.isclose(risultato["regole"]["massimo"]["realized_uscite_salve"], -5.0)


def test_analizza_uscite_soglia_default_e_quella_di_produzione():
    """Coerenza con la misura degli ingressi: stessa soglia 0.30."""
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    eventi = [
        _evento_uscita(decision_at, "HOOD", [
            _sig(date(2026, 9, 1), "HOOD", 10.78, 0.4815, conf=0.70),
            _sig(date(2026, 9, 1), "HOOD", 11.02, 0.0228, conf=0.25),
        ], realized=-23.06),
    ]
    # Soglia custom = 0.50 (sopra il picco 0.4815): nessuna salva.
    r_alta = analizza_uscite_sotto_soglia(eventi, soglia=0.50)
    assert r_alta["regole"]["massimo"]["n_uscite_salve"] == 0
    # Soglia default = 0.30: il picco 0.4815 salva.
    r_bassa = analizza_uscite_sotto_soglia(eventi)
    assert r_bassa["regole"]["massimo"]["n_uscite_salve"] == 1


def test_riepilogo_uscite_leggibile_menziona_caso_vuoto_senza_crashare():
    """Stesso pattern del riepilogo ingressi: i None non esplodono."""
    risultato = {
        "n_uscite_totali": 0,
        "realized_medio_uscite": None,
        "regole": {
            r: {"n_uscite": 0, "n_uscite_salve": 0,
                "realized_uscite_salve": None}
            for r in RULES
        },
    }
    testo = riepilogo_uscite_leggibile(risultato)
    assert "0 chiusure" in testo
    assert "salve" in testo  # la colonna c'e', anche se tutti zeri


def test_riepilogo_uscite_leggibile_riporta_salve_per_regola():
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    eventi = [
        _evento_uscita(decision_at, "A", [
            _sig(date(2026, 9, 1), "A", 10.0, 0.40),
            _sig(date(2026, 9, 1), "A", 11.0, 0.10),
        ], realized=-5.0),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    testo = riepilogo_uscite_leggibile(risultato)
    # massimo salva A (0.40 >= 0.30): la riga di massimo contiene "1" fra salve e fwd
    righe_m = [r for r in testo.splitlines() if r.startswith("massimo")]
    assert "1" in righe_m[0]