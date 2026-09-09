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
    ATTRIBUTION_ISSUER,
    BASELINE,
    MEZZA_VITA_ORE,
    RULES,
    RULES_169,
    RULES_ISSUER,
    SOGLIA_GATE,
    analizza_uscite_sotto_soglia,
    applica_attribution,
    confronto_con_460,
    copertura_issuer,
    costruisci_eventi_uscita,
    dedup_score,
    scelta_issuer_first,
    scelta_issuer_or_fallback_clean,
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
    issuer: bool = False,
) -> dict:
    """Un segnale come li produce `leggi_segnali` (giorno, orario, score, fwd).

    `issuer` e' il campo v2: True quando l'attribution del dossier per quel
    `signal_id` e' ISSUER_SPECIFIC. Il default False e' quello di produzione —
    un segnale senza riga `news_log` (fallback FinBERT) non ha attribution e
    non e' issuer-specific.
    """
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
        "issuer_specific": issuer,
    }


D = date(2026, 8, 27)


# ── Le regole di dedup ────────────────────────────────────────────────────────


def test_le_regole_candidate_sono_esattamente_quelle_della_issue():
    # Le 5 del corpo della issue restano quelle, alla lettera: la v2 e'
    # additiva, e questo test e' il vincolo che glielo impone.
    assert set(RULES_169) == {
        "ultimo_prod", "ultimo", "massimo", "media_conf", "media_decay"
    }


def test_le_regole_v2_sono_additive_e_non_riscrivono_quelle_della_issue():
    assert set(RULES_ISSUER) == {"issuer_first", "issuer_or_fallback_clean"}
    assert not set(RULES_169) & set(RULES_ISSUER)
    # L'ordine conta: le righe della tabella e le chiavi del JSON restano
    # nell'ordine di #460, con le nuove in coda.
    assert RULES == RULES_169 + RULES_ISSUER


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
    # Ogni regola conosciuta parte dallo stesso score: cosi' un'osservazione
    # sintetica resta valida quando la lista delle regole si allunga (v2), e
    # `regole_extra` continua a isolare la sola regola sotto test.
    scores = dict.fromkeys(RULES, score)
    scores.update(regole_extra or {})
    return {
        "giorno": giorno.isoformat(), "symbol": symbol, "n": 1,
        "scores": scores, "min_score": score, "max_score": score,
        "ensemble_prod": True,  # un solo segnale: non fallback
        "ensemble_ultimo": True,
        "n_issuer": 0, "issuer_prod": False,
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

# ── v2 (2026-09-09): le regole issuer-first ──────────────────────────────────
#
# Il buco che queste regole chiudono: la misura #460 ha confrontato solo
# funzioni degli score (ultimo/massimo/medie) — ha misurato il dedup
# intra-ticker, mai la QUALITA' DEL CONTENUTO dentro il dedup. Le ricorrenze
# documentate a mano (MU 30/07, HOOD 01/09, INTC 27/08 e 08/09) sono tutte
# dello stesso tipo: un fan-out macro piu' recente sostituisce, come stato del
# ticker, una notizia issuer-specific forte.


def test_issuer_first_senza_issuer_specific_e_la_baseline():
    """Zero issuer-specific nel giorno: la regola non ha informazione, non agisce.

    E' il vincolo che rende l'estensione additiva: dove l'attribution non dice
    niente le regole v2 non possono spostare il numero, e ogni scarto dalla
    baseline resta attribuibile all'attribution.
    """
    gruppo = [
        _sig(D, "MU", 15.0, 0.565, fallback=True),
        _sig(D, "MU", 16.0, 0.037),
    ]
    assert dedup_score(gruppo, "issuer_first") == dedup_score(gruppo, BASELINE)
    assert scelta_issuer_first(gruppo) is scelta_produzione(gruppo)


def test_issuer_first_con_un_solo_issuer_specific_lo_sceglie_anche_se_vecchio():
    """MU 30/07 alla lettera: il picco issuer-specific batte il fan-out recente.

    Sotto il ranker vero vince il +0.037 delle 16:01 (ensemble piu' recente);
    sotto `issuer_first` vince il +0.565 delle 15:00, che e' la notizia
    sull'emittente.
    """
    picco = _sig(D, "MU", 15.0, 0.565, issuer=True)
    fanout = _sig(D, "MU", 16.0, 0.037)
    gruppo = [picco, fanout]
    assert dedup_score(gruppo, BASELINE) == 0.037
    assert dedup_score(gruppo, "issuer_first") == 0.565
    assert scelta_issuer_first(gruppo) is picco


def test_issuer_first_con_piu_issuer_specific_prende_il_piu_recente():
    """Dentro la classe issuer-specific la sola chiave e' la freschezza.

    Due notizie sull'emittente nello stesso giorno: la piu' recente e' lo
    stato del ticker, esattamente come fa il ranker dentro la sua classe.
    """
    gruppo = [
        _sig(D, "INTC", 9.0, 0.228, issuer=True),
        _sig(D, "INTC", 14.0, 0.410, issuer=True),   # piu' recente
        _sig(D, "INTC", 17.0, 0.000),                # fan-out, ignorato
    ]
    assert dedup_score(gruppo, "issuer_first") == 0.410


def test_issuer_first_ignora_la_preferenza_ensemble_dentro_la_classe_issuer():
    """La differenza voluta con `issuer_or_fallback_clean`.

    `issuer_first` guarda solo la freschezza dentro la classe issuer-specific:
    un issuer-specific fallback ma piu' recente vince. E' cio' che isola quanto
    pesa il secondo criterio, misurato dall'altra regola.
    """
    gruppo = [
        _sig(D, "AAPL", 10.0, 0.50, issuer=True),                 # ensemble
        _sig(D, "AAPL", 11.0, 0.20, issuer=True, fallback=True),  # piu' recente
    ]
    assert dedup_score(gruppo, "issuer_first") == 0.20
    assert dedup_score(gruppo, "issuer_or_fallback_clean") == 0.50


def test_issuer_or_fallback_clean_su_giorno_di_solo_fanout_e_la_baseline():
    """Fan-out puro: nessun issuer-specific, la regola degrada sulla baseline.

    Il ranker preferisce l'ensemble al fallback piu' recente; senza
    issuer-specific la regola v2 deve fare esattamente lo stesso.
    """
    gruppo = [
        _sig(D, "SPY", 10.0, 0.31),                 # ensemble
        _sig(D, "SPY", 15.0, -0.44, fallback=True),  # fallback piu' recente
    ]
    assert dedup_score(gruppo, "issuer_or_fallback_clean") == 0.31
    assert dedup_score(gruppo, "issuer_or_fallback_clean") == dedup_score(gruppo, BASELINE)


def test_issuer_or_fallback_clean_ordina_issuer_poi_non_fallback_poi_resto():
    """Le tre classi in ordine, ciascuna col suo tie-break di freschezza."""
    issuer_fallback = _sig(D, "HOOD", 9.0, 0.48, issuer=True, fallback=True)
    ensemble_recente = _sig(D, "HOOD", 12.0, 0.02)
    fallback_recentissimo = _sig(D, "HOOD", 18.0, -0.30, fallback=True)
    gruppo = [issuer_fallback, ensemble_recente, fallback_recentissimo]
    # l'issuer-specific vince anche se e' fallback e il piu' vecchio
    assert scelta_issuer_or_fallback_clean(gruppo) is issuer_fallback
    # senza issuer-specific vincerebbe il non-fallback, non il piu' recente
    senza_issuer = [ensemble_recente, fallback_recentissimo]
    assert scelta_issuer_or_fallback_clean(senza_issuer) is ensemble_recente


def test_le_regole_v2_su_un_solo_segnale_sono_quel_segnale():
    for issuer in (True, False):
        gruppo = [_sig(D, "X", 10.0, 0.42, issuer=issuer)]
        assert dedup_score(gruppo, "issuer_first") == 0.42
        assert dedup_score(gruppo, "issuer_or_fallback_clean") == 0.42


def test_le_regole_v2_sono_deterministiche_sullordine_di_ingresso():
    """Stesso gruppo, ordine di lista diverso: stesso punteggio.

    `raggruppa_per_simbolo_giorno` ordina per `generated_at`, ma la regola non
    deve dipendere da quell'ordinamento per essere corretta.
    """
    segnali = [
        _sig(D, "NOW", 9.0, 0.14, issuer=True),
        _sig(D, "NOW", 13.0, 0.31, issuer=True),
        _sig(D, "NOW", 16.0, -0.20),
        _sig(D, "NOW", 11.0, 0.05, fallback=True),
    ]
    for regola in RULES_ISSUER:
        atteso = dedup_score(segnali, regola)
        assert dedup_score(list(reversed(segnali)), regola) == atteso
        assert dedup_score([segnali[2], segnali[0], segnali[3], segnali[1]], regola) == atteso


def test_le_regole_v2_non_mutano_le_regole_della_issue():
    """Nessuna riga di #460 cambia perche' esistono le regole v2.

    Il controllo e' su un gruppo che le regole v2 spostano davvero (c'e' un
    issuer-specific non piu' recente): le 5 regole originali devono restituire
    gli stessi numeri che restituivano prima.
    """
    gruppo = [
        _sig(D, "MU", 15.0, 0.565, conf=0.9, issuer=True),
        _sig(D, "MU", 16.0, 0.037, conf=0.5),
    ]
    assert dedup_score(gruppo, "ultimo_prod") == 0.037
    assert dedup_score(gruppo, "ultimo") == 0.037
    assert dedup_score(gruppo, "massimo") == 0.565
    assert dedup_score(gruppo, "media_conf") == (
        (0.565 * 0.9 + 0.037 * 0.5) / 1.4
    )
    # media_decay resta la stessa funzione degli score/orari: la si ricalcola
    # a mano, senza il flag issuer, e i due valori devono coincidere.
    senza_flag = [{k: v for k, v in s.items() if k != "issuer_specific"} for s in gruppo]
    assert dedup_score(senza_flag, "media_decay") == dedup_score(gruppo, "media_decay")


def test_dedup_score_senza_campo_issuer_non_esplode_e_vale_la_baseline():
    """Righe senza attribution (fallback FinBERT, dati storici): default sicuro.

    Il dossier lascia `UNKNOWN` un segnale senza riga `news_log`: qui il
    corrispettivo e' l'assenza del campo, che non deve promuovere niente.
    """
    gruppo = [
        {k: v for k, v in _sig(D, "Z", 10.0, 0.50).items() if k != "issuer_specific"},
        {k: v for k, v in _sig(D, "Z", 11.0, 0.10).items() if k != "issuer_specific"},
    ]
    assert dedup_score(gruppo, "issuer_first") == dedup_score(gruppo, BASELINE)
    assert dedup_score(gruppo, "issuer_or_fallback_clean") == dedup_score(gruppo, BASELINE)


# ── v2: attribution e copertura ──────────────────────────────────────────────


def test_applica_attribution_marca_solo_issuer_specific():
    segnali = [
        dict(_sig(D, "A", 10.0, 0.4), signal_id=1),
        dict(_sig(D, "A", 11.0, 0.1), signal_id=2),
        dict(_sig(D, "A", 12.0, 0.2), signal_id=3),
    ]
    copertura = applica_attribution(
        segnali, {1: ATTRIBUTION_ISSUER, 2: "FANOUT"}
    )
    assert [s["issuer_specific"] for s in segnali] == [True, False, False]
    # il signal_id 3 non e' nella mappa: nessuna attribution, nessuna promozione
    assert copertura["segnali_con_attribution"] == 2
    assert copertura["segnali_totali"] == 3
    assert copertura["conteggi"]["SENZA_ATTRIBUTION"] == 1
    assert copertura["conteggi"][ATTRIBUTION_ISSUER] == 1


def test_applica_attribution_su_lista_vuota_non_divide_per_zero():
    copertura = applica_attribution([], {})
    assert copertura["quota_con_attribution"] is None
    assert copertura["segnali_totali"] == 0


def test_riduci_registra_quanti_issuer_specific_ha_il_simbolo_giorno():
    segnali = [
        _sig(D, "MU", 15.0, 0.565, issuer=True, fwd_1d=0.18),
        _sig(D, "MU", 16.0, 0.037, fwd_1d=0.18),
        _sig(D, "SPY", 10.0, 0.10, fwd_1d=0.01),
    ]
    oss = {o["symbol"]: o for o in riduci_a_simbolo_giorno(segnali)}
    assert oss["MU"]["n_issuer"] == 1
    # il ranker sceglie il fan-out delle 16:00: NON stava gia' su un issuer
    assert oss["MU"]["issuer_prod"] is False
    assert oss["SPY"]["n_issuer"] == 0
    assert oss["MU"]["scores"]["issuer_first"] == 0.565
    assert oss["MU"]["scores"]["ultimo_prod"] == 0.037


def test_copertura_issuer_separa_il_margine_di_manovra():
    """Dove il ranker sceglieva GIA' un issuer-specific la regola v2 non corregge.

    Senza questa separazione un IC identico alla baseline non si sa leggere:
    regola inefficace o regola senza occasioni?
    """
    osservazioni = [
        {"n_issuer": 0, "issuer_prod": False},
        {"n_issuer": 2, "issuer_prod": True},   # gia' issuer: niente da correggere
        {"n_issuer": 1, "issuer_prod": False},  # margine di manovra
        {"n_issuer": 3, "issuer_prod": False},  # margine di manovra
    ]
    c = copertura_issuer(osservazioni)
    assert c["simbolo_giorni"] == 4
    assert c["con_almeno_un_issuer"] == 3
    assert c["baseline_gia_issuer"] == 1
    assert c["margine_di_manovra"] == 2
    assert c["quota_con_issuer"] == 0.75


def test_copertura_issuer_su_campione_vuoto_non_divide_per_zero():
    assert copertura_issuer([])["quota_con_issuer"] is None


def test_statistiche_gate_conta_i_flip_delle_regole_v2_contro_la_baseline():
    """Il caso INTC: l'issuer-specific passa il gate dove il fan-out lo skippa."""
    osservazioni = riduci_a_simbolo_giorno([
        _sig(D, "INTC", 9.0, 0.42, issuer=True, fwd_1d=0.03),
        _sig(D, "INTC", 17.0, 0.00, fwd_1d=0.03),
    ])
    st = statistiche_gate(osservazioni)
    assert st[BASELINE]["n_sopra_soglia"] == 0
    assert st["issuer_first"]["n_sopra_soglia"] == 1
    assert st["issuer_first"]["n_flip_persi"] == 1
    assert st["issuer_first"]["n_flip_evitati"] == 0
    assert st["issuer_first"]["media_fwd_1d_flip_persi"] == 0.03


def test_misura_espone_le_regole_v2_nelle_stesse_strutture_di_460():
    """Chiavi additive: stessa struttura, due righe in piu'."""
    osservazioni = riduci_a_simbolo_giorno([
        _sig(D, s, 10.0, v, issuer=(i % 2 == 0), fwd_1d=v / 10)
        for i, (s, v) in enumerate(
            [("A", 0.5), ("B", 0.4), ("C", 0.3), ("D", 0.2), ("E", 0.1), ("F", -0.2)]
        )
    ])
    risultato = misura(osservazioni, "2026-06-15", "2026-08-29", {"segnali_totali": 6})
    for nome in ("tutti", "ensemble"):
        assert set(risultato["ic_sintesi"][nome].keys()) == set(RULES)
        assert set(risultato["serie_giornaliera_1g"][nome].keys()) == set(RULES)
        for regola in RULES_ISSUER:
            assert regola in risultato["gate_0.30"][nome]
    assert risultato["finestra"]["until"] == "2026-08-29"
    assert risultato["attribution"] == {"segnali_totali": 6}
    assert risultato["copertura_issuer"]["simbolo_giorni"] == 6
    # il riepilogo stampa le due righe nuove senza esplodere
    testo = riepilogo_leggibile(risultato)
    assert "issuer_first" in testo
    assert "issuer_or_fallback_clean" in testo
    assert "margine di manovra" in testo


def test_analizza_uscite_regola_issuer_salva_la_posizione_hood():
    """HOOD 01/09: l'upgrade Morgan Stanley e' issuer-specific, il meme coin no.

    Sotto le regole v2 la posizione non sarebbe uscita per `below_entry_gate`
    (+0,4815 >= 0,30): e' il flip salvato lato uscita, e vale solo perche' la
    regola d'uscita e' la stessa dell'ingresso.
    """
    decision_at = datetime(2026, 9, 1, 12, 37, tzinfo=UTC)
    g = date(2026, 9, 1)
    eventi = [
        _evento_uscita(decision_at, "HOOD", [
            _sig(g, "HOOD", 10.78, 0.4815, issuer=True),  # upgrade MS
            _sig(g, "HOOD", 11.02, 0.0228),               # fan-out meme coin
        ], realized=-23.06),
    ]
    risultato = analizza_uscite_sotto_soglia(eventi)
    assert risultato["regole"][BASELINE]["n_uscite_salve"] == 0
    for regola in RULES_ISSUER:
        assert risultato["regole"][regola]["n_uscite_salve"] == 1
        assert risultato["regole"][regola]["realized_uscite_salve"] == -23.06


# ── v2: riconciliazione con l'artefatto congelato di #460 ────────────────────


def _artefatto(**override) -> dict:
    """Un artefatto minimale nella forma di `misura`, con le 5 regole di #460."""
    base = {
        "ic_sintesi": {
            sub: {
                r: {h: {"giorni": 55, "ic_medio": -0.02} for h in ("1g", "3g", "5g")}
                for r in RULES
            }
            for sub in ("tutti", "ensemble")
        },
        "gate_0.30": {
            sub: dict(
                {r: {"n_sopra_soglia": 10, "media_fwd_1d_sopra_soglia": -0.001}
                 for r in RULES},
                n_campione=3047, media_fwd_1d_campione=-0.0009,
            )
            for sub in ("tutti", "ensemble")
        },
        "serie_giornaliera_1g": {
            sub: {r: [{"giorno": "2026-06-15", "ic": 0.1, "n_simboli": 20}]
                  for r in RULES}
            for sub in ("tutti", "ensemble")
        },
    }
    for chiave, valore in override.items():
        base[chiave] = valore
    return base


def test_confronto_460_senza_artefatto_di_riferimento_lo_dice():
    esito = confronto_con_460(_artefatto(), None)
    assert esito["disponibile"] is False


def test_confronto_460_su_run_identica_non_trova_scarti():
    esito = confronto_con_460(_artefatto(), _artefatto())
    assert esito["n_scarti"] == 0
    assert esito["scarti"] == []


def test_confronto_460_ignora_le_regole_v2_assenti_dal_riferimento():
    """Il riferimento #460 non ha le regole v2: la loro assenza non e' uno scarto.

    E' il senso di "additivo": il confronto guarda solo le 5 righe che
    esistevano prima.
    """
    v1 = _artefatto()
    for sub in ("tutti", "ensemble"):
        for regola in RULES_ISSUER:
            del v1["ic_sintesi"][sub][regola]
            del v1["gate_0.30"][sub][regola]
            del v1["serie_giornaliera_1g"][sub][regola]
    esito = confronto_con_460(_artefatto(), v1)
    assert esito["n_scarti"] == 0


def test_confronto_460_registra_lo_scarto_su_una_regola_originale():
    """Se una regola di #460 si muove, la run lo dice — non lo nasconde."""
    v2 = _artefatto()
    v2["ic_sintesi"]["tutti"]["massimo"]["1g"]["ic_medio"] = -0.03
    esito = confronto_con_460(v2, _artefatto())
    assert esito["n_scarti"] == 1
    assert esito["scarti"][0]["campo"] == "ic_sintesi.tutti.massimo.1g.ic_medio"
    assert esito["n_scarti_orizzonte_1g_e_gate"] == 1


def test_confronto_460_separa_gli_scarti_di_orizzonte_3g_5g():
    """Il worker forward-return riempie 3g/5g anche dopo la pubblicazione.

    Quello scarto e' un fatto sui DATI, non sulle regole: va registrato e
    distinto da uno scarto su 1g o sul gate, che invece invaliderebbe
    l'additivita'.
    """
    v2 = _artefatto()
    v2["ic_sintesi"]["tutti"]["ultimo_prod"]["5g"]["giorni"] = 51
    esito = confronto_con_460(v2, _artefatto())
    assert esito["n_scarti"] == 1
    assert esito["n_scarti_orizzonte_1g_e_gate"] == 0
