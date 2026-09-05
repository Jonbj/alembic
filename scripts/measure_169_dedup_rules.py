#!/usr/bin/env python3
"""Misura la varianza intraday dei segnali S4 e confronta le regole di dedup (issue #169).

Il ranker S4 usa il segnale **piu' recente** per ticker: il 2026-07-30 il picco
+0.565 di MU (17:45) e' stato sovrascritto 16 minuti dopo da un +0.037, e MU e'
stata skippata con `score 0.005 < 0.300` nello stesso giorno in cui faceva
+18,4%. La issue apre la domanda — quale regola di dedup rappresenterebbe
meglio il peso della notizia: ultimo (produzione), massimo, media pesata per
confidenza, o una finestra temporale — e chiede la MISURA, non la decisione.
La decisione e' taratura e ricade nel freeze #171; questo script non tocca il
ranker e non cambia alcun parametro di produzione.

METODO — la parte che decide la validita' del numero.

  1. Riduzione a UNA osservazione per simbolo-giorno. Il segnale scelto e il
     forward return che fa da target sono quelli del ranker DI PRODUZIONE:
     `DISTINCT ON (symbol) ... ORDER BY symbol, fallback_used ASC,
     generated_at DESC` (`_FETCH_SIGNALS_FOR_CYCLE`, src/store/pg_store.py) —
     vince prima il non-fallback, e solo a parita' di stato il piu' recente.
     I forward return 1/3/5 giorni sono quelli che il worker quotidiano
     (`run_forward_return_worker`) scrive su `sentiment_signals`: nessuna
     nuova fonte dati, nessuna Alpaca call. I simbolo-giorni il cui segnale
     scelto non ha ancora il forward return restano fuori (troppo recenti),
     senza spostare la scelta verso un segnale piu' vecchio.

  2. Per ogni simbolo-giorno le regole candidate assegnano un punteggio:
       - `ultimo_prod` : cosa fa il ranker OGGI, alla lettera — preferenza
                     ensemble e poi recenza. E' la BASELINE contro cui si
                     contano i flip;
       - `ultimo`   : l'ultimo per solo orario, cioe' la riduzione di
                     `compute_s4_ic.py`. NON e' il ranker: ignora la
                     preferenza ensemble. Resta misurata perche' la distanza
                     fra le sue righe e quelle di `ultimo_prod` quantifica
                     quanto quell'approssimazione costa;
       - `massimo` : il picco del giorno, ignora la sequenza;
       - `media_conf` : media degli score pesata per confidenza;
       - `media_decay` : la "finestra temporale" — media pesata con
                     decadimento esponenziale (mezza vita MEZZA_VITA_ORE,
                     riferimento = mezzanotte UTC di fine giornata). Una
                     finestra a taglio duro e' stata scartata perche' il
                     campione cambierebbe da regola a regola e gli IC non
                     sarebbero confrontabili.

  3. Le regole si confrontano sullo STESSO campione con due metriche:
       - IC Spearman cross-sectional giorno per giorno (>= MIN_SIMBOLI_GIORNO
         simboli, serie costanti scartate), media e t sui giorni — le stesse
         guardie di `compute_s4_ic.py`;
       - gate a SOGLIA_GATE (il floor di produzione, NON una taratura: qui si
         misura, non si cambia): per ogni regola quanti simbolo-giorni passa e
         con che forward return medio, e i **flip** contro `ultimo_prod`: quanti
         ingressi il ranker attuale perde (regola >= soglia > ultimo) e quanti
         falsi positivi eviterebbe (ultimo >= soglia > regola), con il forward
         return medio di ciascun lato.

Output: `docs/evidence/s4_dedup_rules_169.json` (corpo della issue, gate
d'ingresso) e `docs/evidence/s4_dedup_rules_169_uscite.json` (follow-up
2026-09-01, gate d'uscita via below_entry_gate). Idempotente, sola lettura
sul DB. NON e' un test, NON ha soglie pre-registrate, NON decide la regola.

Uso:
    python scripts/measure_169_dedup_rules.py
    python scripts/measure_169_dedup_rules.py --since 2026-06-15
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scipy.stats import spearmanr

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT = PROJECT_DIR / "docs" / "evidence" / "s4_dedup_rules_169.json"
OUT_USCITE = PROJECT_DIR / "docs" / "evidence" / "s4_dedup_rules_169_uscite.json"

# Le candidate della issue, esattamente quelle: la decisione su quale adottare
# e' dell'operatore (ready-for-human), non dello script.
RULES = ("ultimo_prod", "ultimo", "massimo", "media_conf", "media_decay")
# La baseline contro cui si contano i flip: la regola che il ranker applica
# davvero (`ultimo_prod`), non l'approssimazione di compute_s4_ic.py.
BASELINE = "ultimo_prod"

# Parametri di STRUMENTAZIONE, non di taratura: il ranker in produzione non
# cambia. Il gate misura i flip alla soglia di produzione; la mezza vita e' il
# modo piu' semplice di fare "finestra temporale" senza cambiare campione fra
# regole; il minimo di simboli e' la stessa guardia di compute_s4_ic.py.
SOGLIA_GATE = 0.30  # loss_feedback.threshold_baseline, floor del gate S4
MEZZA_VITA_ORE = 6.0
MIN_SIMBOLI_GIORNO = 5  # sotto, la correlazione cross-sectional e' rumore puro

QUERY = """\
SELECT date_trunc('day', generated_at)::date, symbol, score, confidence, fallback_used,
       extract(epoch from generated_at)::bigint,
       coalesce(forward_return::text, ''), coalesce(forward_return_3d::text, ''),
       coalesce(forward_return_5d::text, '')
FROM sentiment_signals
WHERE generated_at >= '{since}'
ORDER BY generated_at;"""


# ─── Lettura DB: docker exec psql, stessa firma di compute_s4_ic.py ───────────


def leggi_segnali(since: str) -> list[dict]:
    """Tutti i segnali dalla finestra, in ordine di generazione.

    Nessun filtro sul forward return: l'ultimo segnale del simbolo-giorno e'
    sempre l'ultimo vero, anche se il suo forward return non e' ancora stato
    calcolato (in quel caso l'osservazione esce dal campione, non si ribia'
    la scelta verso un segnale piu' vecchio).
    """
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", QUERY.format(since=since)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:200]}")

    out: list[dict] = []
    for riga in res.stdout.splitlines():
        if not riga.strip():
            continue
        p = riga.split("|", 9)
        if len(p) < 9:
            continue
        out.append(
            {
                "giorno": date.fromisoformat(p[0]),
                "symbol": p[1],
                "generated_at": datetime.fromtimestamp(int(p[5]), tz=timezone.utc),
                "score": float(p[2]),
                "confidence": float(p[3]),
                "fallback": p[4] == "t",
                "fwd_1d": float(p[6]) if p[6] else None,
                "fwd_3d": float(p[7]) if p[7] else None,
                "fwd_5d": float(p[8]) if p[8] else None,
            }
        )
    return out


# ─── Funzioni di misura: pure, testabili senza DB ────────────────────────────


def raggruppa_per_simbolo_giorno(segnali: list[dict]) -> dict[tuple[date, str], list[dict]]:
    """Un gruppo per (giorno, simbolo), ciascuno in ordine di generazione."""
    gruppi: dict[tuple[date, str], list[dict]] = defaultdict(list)
    for s in segnali:
        gruppi[(s["giorno"], s["symbol"])].append(s)
    for gruppo in gruppi.values():
        gruppo.sort(key=lambda s: s["generated_at"])
    return dict(gruppi)


def scelta_produzione(gruppo: list[dict]) -> dict:
    """Il segnale che il ranker sceglierebbe: l'ordinamento di produzione.

    `_FETCH_SIGNALS_FOR_CYCLE` in `src/store/pg_store.py` fa
    `ORDER BY ss.symbol, ss.fallback_used ASC, ss.generated_at DESC` con
    `DISTINCT ON (ss.symbol)`: fra i segnali del simbolo vince PRIMA il non
    fallback, e solo a parita' di stato il piu' recente. Un fallback FinBERT
    arrivato dopo un ensemble NON lo sovrascrive.
    """
    if not gruppo:
        raise ValueError("gruppo vuoto")
    return min(gruppo, key=lambda s: (s["fallback"], -s["generated_at"].timestamp()))


def dedup_score(gruppo: list[dict], regola: str, mezza_vita_ore: float = MEZZA_VITA_ORE) -> float:
    """Punteggio del simbolo-giorno secondo la regola `regola`.

    `gruppo` sono i segnali di UN (giorno, simbolo), in ordine di generazione.
    Nessuna regola inventa informazione: tutte sono funzioni dei soli score
    (e della confidenza/orario gia' presenti su ogni riga).
    """
    if not gruppo:
        raise ValueError("gruppo vuoto")

    if regola == "ultimo_prod":
        # La regola VERA di produzione: preferenza ensemble, poi recenza.
        return scelta_produzione(gruppo)["score"]

    if regola == "ultimo":
        # L'ultimo per solo orario: NON e' cio' che fa il ranker (ignora la
        # preferenza ensemble). Resta misurata perche' e' la riduzione di
        # `compute_s4_ic.py`, e la distanza fra le due righe dice quanto
        # quell'approssimazione costa.
        return gruppo[-1]["score"]

    if regola == "massimo":
        return max(s["score"] for s in gruppo)

    if regola == "media_conf":
        somma_conf = sum(s["confidence"] for s in gruppo)
        if somma_conf > 0:
            return sum(s["score"] * s["confidence"] for s in gruppo) / somma_conf
        # confidenze tutte nulle: la media semplice e' l'unica definita
        return statistics.mean(s["score"] for s in gruppo)

    if regola == "media_decay":
        # Riferimento = mezzanotte UTC di fine giornata: l'eta' di ogni
        # segnale e' quanto e' arrivato prima della chiusura del simbolo-giorno.
        fine_giorno = datetime.combine(
            gruppo[0]["giorno"] + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        )
        pesi = [
            0.5 ** ((fine_giorno - s["generated_at"]).total_seconds() / 3600.0 / mezza_vita_ore)
            for s in gruppo
        ]
        return sum(s["score"] * w for s, w in zip(gruppo, pesi)) / sum(pesi)

    raise ValueError(f"regola sconosciuta: {regola}")


def riduci_a_simbolo_giorno(segnali: list[dict]) -> list[dict]:
    """Una osservazione per (giorno, simbolo): score per ogni regola + fwd.

    Il TARGET (forward return 1/3/5g) e' quello del segnale che il ranker
    sceglie davvero — `scelta_produzione`, cioe' `fallback_used ASC,
    generated_at DESC` — non quello dell'ultimo per solo orario. E' il segnale
    su cui la decisione sarebbe stata presa, quindi e' contro quel futuro che
    ogni regola va misurata; usarne un altro darebbe alle candidate un target
    che il ranker non avrebbe mai visto. Il target e' lo STESSO per tutte le
    regole: le righe restano confrontabili. Se quel segnale non ha ancora il
    forward return, l'osservazione resta nel campione con fwd a None (esce
    dalle medie condizionate e dagli IC dell'orizzonte mancante).
    """
    oss: list[dict] = []
    for (giorno, symbol), gruppo in sorted(
        raggruppa_per_simbolo_giorno(segnali).items()
    ):
        scelto = scelta_produzione(gruppo)
        oss.append(
            {
                "giorno": giorno.isoformat(),
                "symbol": symbol,
                "n": len(gruppo),
                "scores": {regola: dedup_score(gruppo, regola) for regola in RULES},
                "min_score": min(s["score"] for s in gruppo),
                "max_score": max(s["score"] for s in gruppo),
                # Il sottoinsieme "ensemble" = giorni in cui il ranker avrebbe
                # agito su un segnale ensemble (ne esiste almeno uno non
                # fallback), che e' la condizione vera di produzione.
                "ensemble_prod": not scelto["fallback"],
                "ensemble_ultimo": not gruppo[-1]["fallback"],
                "fwd_1d": scelto["fwd_1d"],
                "fwd_3d": scelto["fwd_3d"],
                "fwd_5d": scelto["fwd_5d"],
            }
        )
    return oss


def serie_ic_giornaliera(
    per_giorno: dict[str, list[dict]], regola: str, orizzonte: int,
    min_simboli: int = MIN_SIMBOLI_GIORNO,
) -> list[tuple[str, float, int]]:
    """IC cross-sectional per ogni giorno con abbastanza simboli.

    Le stesse guardie di `compute_s4_ic._serie_ic`: minimo di simboli, serie
    costanti scartate (Spearman non e' definito), niente NaN.
    """
    campo = f"fwd_{orizzonte}d"
    out: list[tuple[str, float, int]] = []
    for giorno, righe in sorted(per_giorno.items()):
        sel = [r for r in righe if r[campo] is not None]
        if len(sel) < min_simboli:
            continue
        scores = [r["scores"][regola] for r in sel]
        fwd = [r[campo] for r in sel]
        if len(set(scores)) < 2 or len(set(fwd)) < 2:
            continue  # serie costante: la correlazione non e' definita
        ic = spearmanr(scores, fwd).correlation
        if ic is not None and not math.isnan(ic):
            out.append((giorno, float(ic), len(sel)))
    return out


def sintesi_ic(serie: list[tuple[str, float, int]]) -> dict:
    """Media, dispersione e t sulla serie giornaliera degli IC.

    Il t si calcola sui GIORNI, non sulle osservazioni: e' il giorno l'unita'
    indipendente, non il singolo simbolo-giorno (formula identica a
    `compute_s4_ic._sintesi`, ripetuta perche' quella e' privata).
    """
    n = len(serie)
    if n < 3:
        return {"giorni": n, "ic_medio": None, "dev_std": None, "t_stat": None,
                "significativo_a_3": False}
    valori = [ic for _, ic, _ in serie]
    media = statistics.mean(valori)
    dev = statistics.stdev(valori)
    if dev == 0:
        return {"giorni": n, "ic_medio": media, "dev_std": 0.0, "t_stat": None,
                "significativo_a_3": False}
    t = media / (dev / math.sqrt(n))
    return {
        "giorni": n,
        "ic_medio": media,
        "dev_std": dev,
        "t_stat": t,
        "significativo_a_3": abs(t) >= 3.0,
        "ic_rilevabile_a_t3": 3.0 * dev / math.sqrt(n),
    }


def media_fwd(righe: list[dict], campo: str = "fwd_1d") -> float | None:
    """Forward return medio sulle righe che lo hanno; None se nessuna."""
    valori = [r[campo] for r in righe if r[campo] is not None]
    return statistics.mean(valori) if valori else None


def statistiche_gate(osservazioni: list[dict], soglia: float = SOGLIA_GATE) -> dict:
    """Il confronto al gate: pass, flip persi, flip evitati, per ogni regola.

    Il campione sono le osservazioni CON forward return 1g (senza target non
    c'e' verdetto). `ultimo` e' la regola di produzione: ogni altra regola si
    misura contro di essa, allo stesso tempo e sullo stesso simbolo-giorno.
    """
    campione = [o for o in osservazioni if o["fwd_1d"] is not None]
    st: dict[str, dict] = {}
    for regola in RULES:
        sopra = [o for o in campione if o["scores"][regola] >= soglia]
        # flip "perso": la candidata passa dove il ranker attuale skippa —
        # il caso INTC/NOW della Week 35, il picco sovrascritto dal fan-out
        perso = [
            o for o in campione
            if o["scores"][regola] >= soglia and o["scores"][BASELINE] < soglia
        ]
        # flip "evitato": il ranker passa dove la candidata non passerebbe —
        # un eventuale vantaggio della regola, non solo il costo
        evitato = [
            o for o in campione
            if o["scores"][BASELINE] >= soglia and o["scores"][regola] < soglia
        ]
        st[regola] = {
            "n_sopra_soglia": len(sopra),
            "media_fwd_1d_sopra_soglia": media_fwd(sopra),
            "n_flip_persi": len(perso),
            "media_fwd_1d_flip_persi": media_fwd(perso),
            "n_flip_evitati": len(evitato),
            "media_fwd_1d_flip_evitati": media_fwd(evitato),
        }
    return st


def varianza_intraday(osservazioni: list[dict]) -> dict:
    """Il contesto che motiva la issue: quanto oscilla il segnale nello stesso giorno.

    Il range e' (max − min) degli score del simbolo-giorno; e' la distanza fra
    la lettura piu' favorevole e quella piu' sfavorevole dello stesso titolo
    nello stesso giorno — cioe' quanto la scelta della regola di dedup puo'
    spostare il punteggio.
    """
    def _mediana(valori: list[float]) -> float | None:
        if not valori:
            return None
        return statistics.median(valori)

    multi = [o for o in osservazioni if o["n"] > 1]
    ranges = [o["max_score"] - o["min_score"] for o in multi]
    return {
        "simbolo_giorni": len(osservazioni),
        "con_piu_segnali": len(multi),
        "quota_con_piu_segnali": (len(multi) / len(osservazioni)) if osservazioni else None,
        "n_segnali_mediano": _mediana([o["n"] for o in osservazioni]),
        "range_mediano": _mediana(ranges),
        "range_massimo": max(ranges) if ranges else None,
        "con_10_segnali_o_piu": sum(1 for o in osservazioni if o["n"] >= 10),
        "con_5_segnali_o_piu": sum(1 for o in osservazioni if o["n"] >= 5),
    }


# ─── Uscite via below_entry_gate (#169 follow-up 2026-09-01) ─────────────────
#
# L'evidenza del 2026-09-01 (HOOD whipsaw: +0,4815 sostituito da +0,0228,
# SELL a 105 min, −$23.06) ha aggiunto un costo che la misura del corpo della
# issue non vedeva: la sostituzione di un segnale forte non skippava solo
# ingressi — chiudeva posizioni aperte via `below_entry_gate`. Il punto dove
# la sostituzione pesa non è il gate 0.30, è il MOMENTO DELL'USCITA: qualunque
# regola si scelga deve valere anche in uscita, non solo nel ranking d'ingresso
# (testo dell'evidenza, 2026-09-01).
#
# Stesse regole, stessa soglia, stessa logica: per ogni chiusura S4 con
# exit_mechanism='below_entry_gate' si guarda che score avrebbe letto il
# ranker VERO al tick di decisione applicando quella regola. Se la candidata
# sarebbe restata >= soglia, l'uscita NON sarebbe scattata — è il flip
# "salvato" lato uscita, simmetrico al flip "perso" lato ingresso.
#
# Convenzione del realized:
#   * `salve` = uscite che la candidata AVREBBE EVITATO: la candidata
#     avrebbe tenuto la posizione aperta, quindi il realized negativo è un
#     costo che non si è preso (segno: negativo, costo evitato).
#   * `perse` = uscite che la candidata AVREBBE AGGIUNTO: il ranker attuale
#     ha tenuto aperto (baseline >= soglia), la candidata avrebbe chiuso —
#     è un costo aggiuntivo (segno: positivo se la tenuta era in gain).
#   * `saldo` = realized_salve + realized_perse: dice se la regola, sulla
#     finestra, avrebbe migliorato/peggiorato il P&L realized delle chiusure
#     below_entry_gate.


def costruisci_eventi_uscita(eventi_raw: list[dict]) -> list[dict]:
    """Filtra i segnali di ogni evento a quelli con generated_at <= decision_at.

    `eventi_raw` e' la lista di chiusure lette dal DB (decision_at, symbol,
    segnali, net_pnl). Un segnale DOPO l'uscita non era visibile al ranker:
    va scartato. Il caso HOOD 09-01 ha il segnale forte a 10:47 e l'uscita
    alle 12:37 — un filtro >= decision_at lo escluderebbe per costruzione.

    Le altre chiavi dell'evento sono passate attraverso (incluso `net_pnl`,
    facoltativo nei test).
    """
    out: list[dict] = []
    for ev in eventi_raw:
        orario = ev["decision_at"]
        ev_out = {k: v for k, v in ev.items() if k != "segnali"}
        ev_out["segnali"] = [s for s in ev["segnali"] if s["generated_at"] <= orario]
        out.append(ev_out)
    return out


def analizza_uscite_sotto_soglia(
    eventi: list[dict], soglia: float = SOGLIA_GATE,
) -> dict:
    """Per ogni regola, quante uscite avrebbe salvato al gate `soglia`.

    Ogni evento è una chiusura S4 con exit_mechanism='below_entry_gate': per
    costruzione la baseline (`ultimo_prod`) ha letto un punteggio < soglia al
    tick di decisione, e il portafoglio ha chiuso la posizione. Le regole
    candidate sono applicate agli stessi segnali; se la candidata >= soglia,
    l'uscita NON sarebbe scattata sotto quella regola.

    Il campione di questa funzione e' SOLO le chiusure effettive via
    below_entry_gate (baseline < soglia per costruzione). Una candidata puo'
    solo SALVARE queste uscite (tenere la posizione aperta). Il lato opposto
    del flip (la candidata CHIUDE una posizione che il ranker attuale ha
    tenuto) non esiste in questo campione: e' un evento diverso, e per
    misurarlo servono osservazioni di posizioni tenute aperte — fuori
    perimetro di questo script.

    Restituisce un dizionario per regola con:
      * n_uscite: numero di chiusure nel campione (uguale per tutte);
      * n_uscite_salve: uscite EVITATE dalla candidata (la candidata avrebbe
        tenuto, costo non preso);
      * realized_uscite_salve: media condizionata del net_pnl sulle uscite
        salvate (None se il campione e' vuoto). Segno negativo = costo evitato.

    La baseline (`ultimo_prod`) ha per costruzione n_salve = 0: e' esattamente
    la regola che ha prodotto le uscite del campione.
    """
    st: dict[str, dict] = {}
    for regola in RULES:
        salve: list[dict] = []
        for ev in eventi:
            segnali = ev["segnali"]
            if not segnali:
                # Caso patologico: nessun segnale visibile al ranker a quel
                # tick. La candidata non puo' produrre uno score: l'uscita
                # resta "non salvata". Non viene contato fra i salvi.
                continue
            score = dedup_score(segnali, regola)
            if score >= soglia:
                salve.append(ev)
        st[regola] = {
            "n_uscite": len(eventi),
            "n_uscite_salve": len(salve),
            "realized_uscite_salve": (
                statistics.mean(e["net_pnl"] for e in salve) if salve else None
            ),
        }
    return {
        "n_uscite_totali": len(eventi),
        "realized_medio_uscite": (
            statistics.mean(e["net_pnl"] for e in eventi) if eventi else None
        ),
        "regole": st,
    }


def riepilogo_uscite_leggibile(risultato: dict) -> str:
    """Riepilogo testuale del lato uscite, allineato allo stile del corpo."""
    def fmt_f(x: float | None) -> str:
        return f"{x:+.2f}" if x is not None else "    -"

    n = risultato["n_uscite_totali"]
    righe = [
        (
            f"Uscite below_entry_gate: {n} chiusure, "
            f"realized medio {fmt_f(risultato['realized_medio_uscite'])}$"
        ),
        (
            f"{'regola':12} {'salve':>6} {'fwd salve':>10}"
        ),
    ]
    for regola in RULES:
        s = risultato["regole"][regola]
        righe.append(
            f"{regola:12} {s['n_uscite_salve']:>6} "
            f"{fmt_f(s['realized_uscite_salve']):>10}"
        )
    return "\n".join(righe)


# ─── Assemblaggio e riepilogo: puri, testabili senza DB ──────────────────────


def misura(osservazioni: list[dict], since: str) -> dict:
    """Da simbolo-giorni a risultato: varianza, IC, gate.

    Tutto tranne il DB: `main` fa solo `segnali` -> `osservazioni` e poi
    chiama qui. E' la parte che decide il numero, quindi deve essere
    testabile senza docker; `since` e' solo etichetta nella sezione finestra.
    """
    per_giorno: dict[str, list[dict]] = defaultdict(list)
    for o in osservazioni:
        per_giorno[o["giorno"]].append(o)

    # Sottoinsiemi: tutti, e solo ensemble (il segnale che il ranker sceglie
    # non e' un fallback FinBERT). Stesso campione per ogni regola dentro il
    # sottoinsieme.
    sottoinsiemi = {
        "tutti": lambda o: True,
        "ensemble": lambda o: o["ensemble_prod"],
    }

    risultato: dict = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "finestra": {
            "since": since,
            "mezza_vita_ore": MEZZA_VITA_ORE,
            "soglia_gate": SOGLIA_GATE,
            "min_simboli_giorno": MIN_SIMBOLI_GIORNO,
        },
        "metodo": (
            "una osservazione per simbolo-giorno; il segnale scelto (e il forward "
            "return che fa da target) e' quello del ranker di produzione: "
            "fallback_used ASC, generated_at DESC (_FETCH_SIGNALS_FOR_CYCLE); "
            "regole ultimo_prod/ultimo/massimo/media_conf/media_decay sullo stesso "
            "campione, dove `ultimo` (ultimo per solo orario) e' la riduzione di "
            "compute_s4_ic.py, misurata per quantificarne lo scarto dal ranker vero; "
            "IC Spearman cross-sectional giornaliero con t sui giorni; "
            "gate 0.30 (floor di produzione) con flip persi/evitati vs `ultimo_prod`. "
            "Limite dichiarato: l'aggregazione e' il giorno solare, non la finestra "
            "mobile di freschezza del singolo ciclo — il forward return esiste a "
            "orizzonte giorni sul segnale, non per ciclo di portfolio"
        ),
        "simbolo_giorni_totali": len(osservazioni),
        "osservazioni_con_fwd_1g": sum(1 for o in osservazioni if o["fwd_1d"] is not None),
        "varianza_intraday": varianza_intraday(osservazioni),
        "ic_sintesi": {},
        "gate_0.30": {},
        "serie_giornaliera_1g": {},
    }

    for nome, filtro in sottoinsiemi.items():
        giorni = {g: [o for o in righe if filtro(o)] for g, righe in per_giorno.items()}
        risultato["ic_sintesi"][nome] = {
            regola: {f"{o}g": sintesi_ic(serie_ic_giornaliera(giorni, regola, o))
                     for o in (1, 3, 5)}
            for regola in RULES
        }
        # le statistiche al gate misurano solo chi ha il target (fwd 1g):
        # il baseline va calcolato sullo stesso campione
        campione = [o for righe in giorni.values() for o in righe
                    if o["fwd_1d"] is not None]
        risultato["gate_0.30"][nome] = {
            # Il baseline incondizionato: senza di lui i forward medi delle
            # pass/flip non si sanno leggere (meglio o pegglio di cosa?).
            "n_campione": len(campione),
            "media_fwd_1d_campione": media_fwd(campione),
            **statistiche_gate(campione),
        }
        risultato["serie_giornaliera_1g"][nome] = {
            regola: [{"giorno": g, "ic": ic, "n_simboli": n}
                     for g, ic, n in serie_ic_giornaliera(giorni, regola, 1)]
            for regola in RULES
        }
    return risultato


def fmt_numero(valore: float | None, spec: str) -> str:
    """Formatta `valore` con `spec`; None (numero non definito) diventa 'n/d'."""
    return f"{valore:{spec}}" if valore is not None else "n/d"


def riepilogo_leggibile(risultato: dict) -> str:
    """Il riepilogo leggibile (stdout) costruito dal risultato.

    Separato da `main` e difeso da `fmt_numero` perche' i casi limite della
    review sono qui: una finestra recente senza forward return fa tornare
    None da `media_fwd`, un campione senza simbolo-giorni multi-segnale fa
    tornare None da `varianza_intraday` — il riepilogo non deve esplodere
    su nessuno dei due.
    """
    def fmt(ic: dict) -> str:
        return f"{ic['ic_medio']:+.4f}" if ic["ic_medio"] is not None else "   -   "
    def fmt_t(ic: dict) -> str:
        return f"{ic['t_stat']:+6.2f}" if ic["t_stat"] is not None else "    -"
    def fmt_f(x: float | None) -> str:
        return f"{x:+.4f}" if x is not None else "     -"

    v = risultato["varianza_intraday"]
    righe = [
        "Varianza intraday (contesto):",
        (
            f"  simbolo-giorni {v['simbolo_giorni']}, con piu' segnali "
            f"{v['con_piu_segnali']} ({(v['quota_con_piu_segnali'] or 0):.1%}), "
            f"n segnali mediano {fmt_numero(v['n_segnali_mediano'], '')}, "
            f"range (max-min) mediano {fmt_numero(v['range_mediano'], '+.3f')} "
            f"(max {fmt_numero(v['range_massimo'], '+.3f')})"
        ),
    ]
    for nome in risultato["ic_sintesi"]:
        gate = risultato["gate_0.30"][nome]
        righe.append(f"\nSottoinsieme: {nome}")
        righe.append(
            f"  campione {gate['n_campione']} simbolo-giorni con fwd 1g, "
            f"media incondizionata {fmt_numero(gate['media_fwd_1d_campione'], '+.4f')}"
        )
        righe.append(
            f"{'regola':12} {'IC 1g':>8} {'t':>6} {'IC 3g':>8} {'IC 5g':>8} "
            f"{'| gate':>5} {'fwd pass':>9} {'| flip persi':>12} {'fwd persi':>9} "
            f"{'| flip evit.':>12} {'fwd evit.':>9}")
        for regola in RULES:
            s1 = risultato["ic_sintesi"][nome][regola]["1g"]
            s3 = risultato["ic_sintesi"][nome][regola]["3g"]
            s5 = risultato["ic_sintesi"][nome][regola]["5g"]
            g = gate[regola]
            righe.append(
                f"{regola:12} {fmt(s1):>8} {fmt_t(s1):>6} {fmt(s3):>8} {fmt(s5):>8} "
                f"{g['n_sopra_soglia']:>5} {fmt_f(g['media_fwd_1d_sopra_soglia']):>9} "
                f"{g['n_flip_persi']:>12} {fmt_f(g['media_fwd_1d_flip_persi']):>9} "
                f"{g['n_flip_evitati']:>12} {fmt_f(g['media_fwd_1d_flip_evitati']):>9}"
            )
    return "\n".join(righe)


# ─── Driver: legge DB, riduce, misura, scrive evidence ───────────────────────


def leggi_uscite_below_entry_gate(since: str) -> list[dict]:
    """Le chiusure S4 con exit_mechanism='below_entry_gate' dal `since`.

    Il join e' `trades.decision_id = execution_decisions.id`: la decision e'
    la riga che ha registrato l'exit_mechanism al momento della chiusura, e
    `tick_time` e' il momento in cui il gate d'ingresso e' stato valutato
    (cioe' l'istante in cui il ranker ha letto il segnale "sotto soglia").
    Per ogni chiusura si raccolgono TUTTI i segnali del simbolo con
    `generated_at <= tick_time` nello stesso giorno UTC: la finestra mobile
    del ranker (4h) taglierebbe il caso HOOD, in cui il segnale forte era di
    105 min prima e quindi dentro la finestra, ma il segnale 'fan-out'
    immediatamente successivo ne era dentro da 14 min.

    NB: serve anche `trades.net_pnl` per la misura del realized salvato.

    Il join NON e' `decision_id = id`: `trades.decision_id` punta alla
    decisione di INGRESSO, mentre la decisione di uscita e' una riga
    separata. Il match e' per `(symbol, exit_time)` (entrambi timestamptz
    con la stessa precisione del broker). Verificato contro la tabella live:
    tutti e 24 i `below_entry_gate` di produzione sono agganciati.
    """
    query = (
        "SELECT ed.tick_time, t.symbol, t.net_pnl "
        "FROM trades t "
        "JOIN execution_decisions ed "
        "  ON ed.symbol = t.symbol AND ed.tick_time = t.exit_time "
        "WHERE ed.exit_mechanism = 'below_entry_gate' "
        f"  AND t.exit_time >= '{since}'::timestamptz "
        "ORDER BY ed.tick_time;"
    )
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query uscite fallita: {res.stderr.strip()[:200]}")

    out: list[dict] = []
    for riga in res.stdout.splitlines():
        if not riga.strip():
            continue
        p = riga.split("|", 2)
        if len(p) < 3:
            continue
        tick_time = datetime.fromisoformat(p[0])
        if tick_time.tzinfo is None:
            tick_time = tick_time.replace(tzinfo=timezone.utc)
        try:
            net_pnl = float(p[2])
        except ValueError:
            net_pnl = 0.0
        out.append({
            "decision_at": tick_time,
            "symbol": p[1],
            "net_pnl": net_pnl,
        })
    return out


def segnali_per_uscita(eventi: list[dict]) -> list[dict]:
    """Per ogni evento di uscita, recupera i segnali del simbolo <= decision_at.

    Una query unica per simbolo e' molto piu' efficiente di N query. La
    finestra e' l'intero giorno del decision_at (in UTC), coerente con la
    misura degli ingressi.
    """
    if not eventi:
        return []
    # Range giorni coperti dai decision_at.
    giorni = sorted({e["decision_at"].date() for e in eventi})
    giorno_min = min(giorni)
    giorno_max = max(giorni) + timedelta(days=1)
    simbuli_unici = sorted({e["symbol"] for e in eventi})

    # Query: tutti i segnali di quei simboli nelle date di interesse. Poi
    # filtriamo lato Python per generated_at <= decision_at (per uscita).
    query = (
        "SELECT date_trunc('day', generated_at)::date, symbol, score, confidence, "
        "       fallback_used, "
        "       extract(epoch from generated_at)::bigint "
        f"FROM sentiment_signals "
        f"WHERE generated_at >= '{giorno_min.isoformat()}'::date "
        f"  AND generated_at < '{giorno_max.isoformat()}'::date "
        f"  AND symbol = ANY(ARRAY[{','.join(repr(s) for s in simbuli_unici)}]) "
        f"ORDER BY generated_at;"
    )
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query segnali-uscite fallita: {res.stderr.strip()[:200]}")

    # Indicizza per (giorno, simbolo) per il filtro lato uscita.
    per_giorno_simbolo: dict[tuple[date, str], list[dict]] = defaultdict(list)
    for riga in res.stdout.splitlines():
        if not riga.strip():
            continue
        p = riga.split("|", 6)
        if len(p) < 6:
            continue
        g = date.fromisoformat(p[0])
        sym = p[1]
        per_giorno_simbolo[(g, sym)].append({
            "giorno": g,
            "symbol": sym,
            "generated_at": datetime.fromtimestamp(int(p[5]), tz=timezone.utc),
            "score": float(p[2]),
            "confidence": float(p[3]),
            "fallback": p[4] == "t",
            "fwd_1d": None, "fwd_3d": None, "fwd_5d": None,
        })

    out: list[dict] = []
    for ev in eventi:
        g = ev["decision_at"].date()
        segnali = list(per_giorno_simbolo.get((g, ev["symbol"]), []))
        ev_out = dict(ev)
        ev_out["segnali"] = segnali
        out.append(ev_out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since",
        default="2026-06-15",
        help="Inizio della finestra (default 2026-06-15, inizio della serie S4).",
    )
    args = parser.parse_args()

    segnali = leggi_segnali(args.since)
    if not segnali:
        raise SystemExit("Nessun segnale nella finestra: niente da misurare.")
    osservazioni = riduci_a_simbolo_giorno(segnali)
    print(
        f"{len(segnali)} segnali -> {len(osservazioni)} simbolo-giorni "
        f"(dal {args.since})"
    )

    risultato = misura(osservazioni, args.since)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(risultato, indent=2, ensure_ascii=False, default=str))
    tmp.replace(OUT)  # atomica: mai un file mezzo scritto
    print(f"Scritto: {OUT}\n")

    print(riepilogo_leggibile(risultato))

    # ── Misura lato uscite (#169 follow-up 2026-09-01) ──────────────────────
    uscite_raw = leggi_uscite_below_entry_gate(args.since)
    uscite_con_segnali = segnali_per_uscita(uscite_raw)
    uscite_eventi = costruisci_eventi_uscita(uscite_con_segnali)
    risultato_uscite = analizza_uscite_sotto_soglia(uscite_eventi)
    risultato_uscite["finestra"] = {
        "since": args.since,
        "soglia_gate": SOGLIA_GATE,
    }
    risultato_uscite["metodo"] = (
        "una chiusura per evento (trades JOIN execution_decisions su decision_id "
        "con exit_mechanism='below_entry_gate'); segnali del simbolo con "
        "generated_at <= decision_at nello stesso giorno UTC; stesse regole e "
        "stessa soglia 0.30 della misura ingressi. Una uscita e' 'salva' se la "
        "candidata >= soglia (la candidata avrebbe tenuto aperto, costo non "
        "preso). Baseline (ultimo_prod) per costruzione n_salve=0."
    )

    tmp_u = OUT_USCITE.with_suffix(".json.tmp")
    tmp_u.write_text(json.dumps(risultato_uscite, indent=2, ensure_ascii=False,
                                 default=str))
    tmp_u.replace(OUT_USCITE)
    print(f"\nScritto: {OUT_USCITE}")
    print(f"\n{riepilogo_uscite_leggibile(risultato_uscite)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())