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

  1. Riduzione a UNA osservazione per simbolo-giorno, la stessa di
     `compute_s4_ic.py` (che tiene l'ultimo segnale del giorno). I forward
     return orizzonte 1/3/5 giorni sono quelli che il worker quotidiano
     (`run_forward_return_worker`) scrive su `sentiment_signals` presi dal
     segnale scelto dal ranker: nessuna nuova fonte dati, nessuna Alpaca call.
     I simbolo-giorni il cui ultimo segnale non ha ancora il forward return
     restano fuori (troppe recenti), senza ribie' la scelta verso un segnale
     piu' vecchio.

  2. Per ogni simbolo-giorno le regole candidate assegnano un punteggio:
       - `ultimo`   : il segnale piu' recente del giorno — cosa fa il ranker
                     oggi. Come `compute_s4_ic.py` e' il semplice ultimo per
                     orario, SENZA la preferenza ensemble del ranker vero
                     (`fallback_used ASC` prima di `generated_at DESC`):
                     e' una approssimazione dichiarata, uguale per le due
                     misure perche' i numeri restino confrontabili;
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
         con che forward return medio, e i **flip** contro `ultimo`: quanti
         ingressi il ranker attuale perde (regola >= soglia > ultimo) e quanti
         falsi positivi eviterebbe (ultimo >= soglia > regola), con il forward
         return medio di ciascun lato.

Output: `docs/evidence/s4_dedup_rules_169.json`. Idempotente, sola lettura
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

# Le candidate della issue, esattamente quelle: la decisione su quale adottare
# e' dell'operatore (ready-for-human), non dello script.
RULES = ("ultimo", "massimo", "media_conf", "media_decay")

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


def dedup_score(gruppo: list[dict], regola: str, mezza_vita_ore: float = MEZZA_VITA_ORE) -> float:
    """Punteggio del simbolo-giorno secondo la regola `regola`.

    `gruppo` sono i segnali di UN (giorno, simbolo), in ordine di generazione.
    Nessuna regola inventa informazione: tutte sono funzioni dei soli score
    (e della confidenza/orario gia' presenti su ogni riga).
    """
    if not gruppo:
        raise ValueError("gruppo vuoto")

    if regola == "ultimo":
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

    I forward return sono quelli del segnale che sceglie il ranker (l'ultimo
    del giorno): e' il punteggio che sarebbe stato usato per decidere, quindi
    e' contro quel futuro che la scelta va misurata. Se quell'ultimo segnale
    non ha ancora il forward return, l'osservazione resta nel campione con
    fwd a None (esce dalle medie condizionate, non dalle IC dove manca il
    target dell'orizzonte).
    """
    oss: list[dict] = []
    for (giorno, symbol), gruppo in sorted(
        raggruppa_per_simbolo_giorno(segnali).items()
    ):
        ultimo = gruppo[-1]
        oss.append(
            {
                "giorno": giorno.isoformat(),
                "symbol": symbol,
                "n": len(gruppo),
                "scores": {regola: dedup_score(gruppo, regola) for regola in RULES},
                "min_score": min(s["score"] for s in gruppo),
                "max_score": max(s["score"] for s in gruppo),
                "ensemble_ultimo": not ultimo["fallback"],
                "fwd_1d": ultimo["fwd_1d"],
                "fwd_3d": ultimo["fwd_3d"],
                "fwd_5d": ultimo["fwd_5d"],
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
            if o["scores"][regola] >= soglia and o["scores"]["ultimo"] < soglia
        ]
        # flip "evitato": il ranker passa dove la candidata non passerebbe —
        # un eventuale vantaggio della regola, non solo il costo
        evitato = [
            o for o in campione
            if o["scores"]["ultimo"] >= soglia and o["scores"][regola] < soglia
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


# ─── Driver: legge DB, riduce, misura, scrive evidence ───────────────────────


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

    per_giorno: dict[str, list[dict]] = defaultdict(list)
    for o in osservazioni:
        per_giorno[o["giorno"]].append(o)

    # Sottoinsiemi: tutti, e solo ensemble (l'ultimo segnale del giorno non e'
    # fallback FinBERT). Stesso campione per ogni regola dentro il sottoinsieme.
    sottoinsiemi = {
        "tutti": lambda o: True,
        "ensemble": lambda o: o["ensemble_ultimo"],
    }

    risultato: dict = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "finestra": {
            "since": args.since,
            "mezza_vita_ore": MEZZA_VITA_ORE,
            "soglia_gate": SOGLIA_GATE,
            "min_simboli_giorno": MIN_SIMBOLI_GIORNO,
        },
        "metodo": (
            "una osservazione per simbolo-giorno (riduzione identica a compute_s4_ic.py: "
            "semplice ultimo segnale del giorno, senza la preferenza ensemble del ranker "
            "vero — approssimazione dichiarata per mantenere i due numeri confrontabili); "
            "regole ultimo/massimo/media_conf/media_decay sullo stesso campione; "
            "IC Spearman cross-sectional giornaliero con t sui giorni; "
            "gate 0.30 (floor di produzione) con flip persi/evitati vs `ultimo`"
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(risultato, indent=2, ensure_ascii=False, default=str))
    tmp.replace(OUT)  # atomica: mai un file mezzo scritto
    print(f"Scritto: {OUT}\n")

    # Riepilogo leggibile: prima la varianza, poi il confronto IC, poi il gate
    v = risultato["varianza_intraday"]
    print("Varianza intraday (contesto):")
    print(
        f"  simbolo-giorni {v['simbolo_giorni']}, con piu' segnali "
        f"{v['con_piu_segnali']} ({(v['quota_con_piu_segnali'] or 0):.1%}), "
        f"n segnali mediano {v['n_segnali_mediano']}, "
        f"range (max-min) mediano {v['range_mediano']:+.3f} "
        f"(max {v['range_massimo']:+.3f})"
    )
    for nome in sottoinsiemi:
        gate = risultato["gate_0.30"][nome]
        print(f"\nSottoinsieme: {nome}")
        print(
            f"  campione {gate['n_campione']} simbolo-giorni con fwd 1g, "
            f"media incondizionata {gate['media_fwd_1d_campione']:+.4f}"
        )
        print(f"{'regola':12} {'IC 1g':>8} {'t':>6} {'IC 3g':>8} {'IC 5g':>8} "
              f"{'| gate':>5} {'fwd pass':>9} {'| flip persi':>12} {'fwd persi':>9} "
              f"{'| flip evit.':>12} {'fwd evit.':>9}")
        for regola in RULES:
            s1 = risultato["ic_sintesi"][nome][regola]["1g"]
            s3 = risultato["ic_sintesi"][nome][regola]["3g"]
            s5 = risultato["ic_sintesi"][nome][regola]["5g"]
            g = gate[regola]
            fmt = lambda s: f"{s['ic_medio']:+.4f}" if s["ic_medio"] is not None else "   -   "
            fmt_t = lambda s: f"{s['t_stat']:+6.2f}" if s["t_stat"] is not None else "    -"
            fmt_f = lambda x: f"{x:+.4f}" if x is not None else "     -"
            print(
                f"{regola:12} {fmt(s1):>8} {fmt_t(s1):>6} {fmt(s3):>8} {fmt(s5):>8} "
                f"{g['n_sopra_soglia']:>5} {fmt_f(g['media_fwd_1d_sopra_soglia']):>9} "
                f"{g['n_flip_persi']:>12} {fmt_f(g['media_fwd_1d_flip_persi']):>9} "
                f"{g['n_flip_evitati']:>12} {fmt_f(g['media_fwd_1d_flip_evitati']):>9}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())