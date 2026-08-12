#!/usr/bin/env python3
"""Misura l'overlap S1∩S4 sui target BUY per ciclo di portfolio (issue #181).

L'overlap S1∩S4 e' la firma che distingue "S4 conferma S1" (overlap basso
e indipendente, S4 aggiunge informazione) da "S4 duplica S1" (overlap
alto, l'overlay non e' incrementale). L'audit strategie del 2026-08-04
(PI-2 in `docs/audits/strategies/PORTFOLIO_INTERACTIONS.md`) l'aveva
lasciata come TODO. La issue #181 chiede la misura.

L'output e' evidenza per la decisione su S4 (ridurre a shadow, rimuovere,
oppure tenere perche' aggiunge info). NON e' un test, NON ha soglia
pre-registrata, e non cambia taratura: la finestra di osservazione
(2026-08-03 → 2026-09-28, issue #171) congela qualunque modifica.

Vincoli espliciti (per ripetere l'errore #207 non si fa'):
  - attribuzione S1/S4 dalla colonna `reason`, MAI da `signal_id` da solo
    (i BUY S1 non hanno signal_id; filtrare per la sua presenza
    scarterebbe il core del book);
  - il "ciclo" di confronto usa la grana temporale di S1 (l'evento
    piu' raro) — non 15 minuti, perche' S1 e' MONTHLY post-#185;
  - la serie e' temporale, mai un singolo aggregato (la media nasconde
    se l'overlap e' strutturale o episodico);
  - il baseline atteso da selezione casuale serve a dire se il numero
    e' "tanto" o "niente" (con sleeve piccole e universo grande, un
    overlap del 30% puo' essere casuale);
  - il caso reversal (S4 BUY dove S1 SELL, coda #182) e' separato dal
    "S4 compra cio' che S1 ignora": piu' grave della semplice
    ridondanza, e' la causa documentata della perdita −$83.86 del
    2026-07-16.

Output: serie per ciclo di confronto, scritta in
`docs/evidence/s1_s4_overlap.json`. Idempotente: ricalcola l'intera
serie ad ogni run, non accumula stato.

Uso:
    uv run python scripts/measure_181_overlap.py
    uv run python scripts/measure_181_overlap.py --since 2026-06-15
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT = PROJECT_DIR / "docs" / "evidence" / "s1_s4_overlap.json"

# Universo S1 (config strategies.yaml). Documentato qui perche' serve al
# baseline atteso da selezione casuale. Cambiare questo numero e'
# taratura (freeze), quindi chi vuole rifare il conto su un universo
# diverso deve passare l'argomento --universe.
DEFAULT_UNIVERSE_SIZE = 96

# Granularita' del "ciclo" S1 per il confronto. S1 e' MONTHLY post #185
# ma in era pre-fix ribilanciava piu' spesso. La finestra scelta copre
# entrambi i regimi senza imputare: la finestra e' ampia, e se S4
# tocca un ticker fra una decisione S1 e la successiva, lo contiamo nel
# ciclo della S1 precedente. Niente eventi S1 sfuggono perche' il
# confronto si appoggia al timestamp della decisione S1.
DEFAULT_CYCLE_WINDOW = timedelta(days=30)


# ─── I/O DB: stessa firma di compute_s4_ic.py, docker exec psql ────────────


QUERY_DECISIONS = """\
SELECT tick_time, symbol, decision, reason, signal_id, score, exit_mechanism
FROM execution_decisions
WHERE decision IN ('BUY', 'SELL')
  AND tick_time >= '{since}'
ORDER BY tick_time;"""


def _parse_decision_rows(raw: str) -> list[dict]:
    """Parsa l'output `-t -A -F` di psql in una lista di dict."""
    out: list[dict] = []
    for riga in raw.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        # L'output arriva come: tick_time|symbol|decision|reason|signal_id|score|exit_mechanism
        # `reason` puo' contenere virgole ma non pipe (il codice di
        # portfolio_scheduler non scrive pipe in reason). Quindi split('|')
        # e' sicuro qui. `signal_id` puo' essere vuoto (NULL) → stringa
        # vuota → lo normalizziamo a None per il confronto.
        parts = riga.split("|")
        if len(parts) < 7:
            continue
        out.append(
            {
                "tick_time": datetime.fromisoformat(parts[0]).astimezone(timezone.utc),
                "symbol": parts[1],
                "decision": parts[2],
                "reason": parts[3] or "",
                "signal_id": int(parts[4]) if parts[4] else None,
                "score": float(parts[5]) if parts[5] else 0.0,
                "exit_mechanism": parts[6] or None,
            }
        )
    return out


def _leggi_decisioni(since: datetime) -> list[dict]:
    """Una riga per BUY/SELL, leggendo direttamente dal container Postgres.

    Il `since` viene passato come timestamp ISO8601. La query
    restituisce l'attribuzione S1/S4 *in chiaro* nella colonna
    `reason` — l'attribuzione non e' assunta.
    """
    cmd = [
        "docker", "exec", "alembic-postgres-1", "psql",
        "-U", "trading", "-d", "trading",
        "-t", "-A", "-F", "|",
        "-c", QUERY_DECISIONS.format(since=since.isoformat()),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:300]}")
    return _parse_decision_rows(res.stdout)


# ─── Attribuzione S1/S4 ──────────────────────────────────────────────────────


def split_by_sleeve(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Separa le righe in S1 e S4 sulla base del campo `reason`.

    Convenzione di `reason` (verificata nel codice reale di
    `portfolio_scheduler.py:2600-2620` e nel DB live):
      - `S1 momentum: ...`           → S1
      - `S4 news-driven: ...`        → S4
      - `S4+S1 news-driven: ...`     → entrambi (conteggiato in entrambe)
      - `Portfolio rebalance: ...`   → SELL/EXIT senza strategia; non
        attribuibile. Escluso dal calcolo (un SELL a peso 0 non e' un
        target di alcuna sleeve, e' una chiusura).
      - `score X.XXX < feedback ...` → SKIP_THRESHOLD; non ci interessa
        qui (la issue chiede i target BUY).

    I BUY con `signal_id IS NULL` non sono per forza S1 — la colonna
    `reason` e' l'unica fonte affidabile. Filtrare per `signal_id`
    scarterebbe i BUY S1.
    """
    s1: list[dict] = []
    s4: list[dict] = []
    for row in rows:
        if row["decision"] != "BUY":
            continue
        reason = row.get("reason") or ""
        in_s1 = reason.startswith("S1 momentum") or reason.startswith("S4+S1")
        in_s4 = reason.startswith("S4")
        # Una riga "S4+S1" matcha entrambi i rami, volutamente.
        if in_s1:
            s1.append(row)
        if in_s4:
            s4.append(row)
    return s1, s4


# ─── Funzioni di misura: pure, testabili senza DB ────────────────────────────


def jaccard(a: set, b: set) -> float:
    """Jaccard classica. |A ∩ B| / |A ∪ B|. Coppia vuota → 1.0 (convenzione)."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    inter = a & b
    return len(inter) / len(union)


def weight_correlation(s1: dict, s4: dict) -> float:
    """Correlazione (Pearson) fra i vettori di peso target, allineati
    sull'unione dei simboli.

    Casi degeneri (vettori costanti, intersezione vuota, universo
    disgiunto) → 0.0 per convenzione. La misura risponde alla domanda
    "i pesi si muovono insieme?"; se non c'e' sovrapposizione la
    domanda non e' neppure posta.
    """
    simboli = set(s1) | set(s4)
    if not simboli:
        return 0.0
    # Allinea i pesi: zero dove il ticker manca in una delle due sleeve.
    v1 = [s1.get(s, 0.0) for s in simboli]
    v4 = [s4.get(s, 0.0) for s in simboli]
    n = len(simboli)
    m1 = sum(v1) / n
    m4 = sum(v4) / n
    cov = sum((a - m1) * (b - m4) for a, b in zip(v1, v4)) / n
    sd1 = math.sqrt(sum((a - m1) ** 2 for a in v1) / n)
    sd4 = math.sqrt(sum((b - m4) ** 2 for b in v4) / n)
    if sd1 == 0 or sd4 == 0:
        return 0.0
    return cov / (sd1 * sd4)


def expected_jaccard_random_baseline(
    n_universe: int, n_s1: int, n_s4: int
) -> float:
    """Jaccard attesa se S1 e S4 scegliessero a caso n_s1 e n_s4 ticker
    da un universo di n_universe simboli senza sovrapposizione.

    Formula (per sleeve piccole rispetto all'universo):
        E[|S1 ∩ S4|] ≈ n_s1 * n_s4 / n_universe
        E[|S1 ∪ S4|] ≈ n_s1 + n_s4 - n_s1 * n_s4 / n_universe
    """
    if n_universe <= 0 or n_s1 <= 0 or n_s4 <= 0:
        return 0.0
    e_inter = (n_s1 * n_s4) / n_universe
    e_union = n_s1 + n_s4 - e_inter
    if e_union <= 0:
        return 0.0
    return e_inter / e_union


# ─── Misura per ciclo ────────────────────────────────────────────────────────


def _ticker_weights(buys: list[dict]) -> dict[str, float]:
    """Riduce piu' BUY sullo stesso ticker (nello stesso ciclo) al
    peso medio. Capitano se S4 ha piu' righe BUY sullo stesso ticker
    in finestre ravvicinate; mediando, la misura e' robusta al rumore.
    """
    bucket: dict[str, list[float]] = defaultdict(list)
    for row in buys:
        bucket[row["symbol"]].append(float(row["score"]))
    return {s: sum(ws) / len(ws) for s, ws in bucket.items()}


def compute_per_cycle_overlap(
    s1_buys: list[dict],
    s4_buys: list[dict],
    cycle_window: timedelta,
) -> list[dict]:
    """Costruisce un ciclo per ogni decisione S1, e vi aggrega le S4 BUY
    la cui `tick_time` cade nella finestra `(decisione S1 precedente,
    decisione S1 corrente]`.

    La scelta della granularita' e' di S1 perche' S1 e' l'evento piu'
    raro. I BUY S4 che non cadono in nessuna finestra (prima del primo
    S1) non sono conteggiati: la misura risponde alla domanda
    "cosa fa S4 quando S1 compra?", non "cosa fa S4 in assoluto".

    Piu' S1 BUY allo stesso `tick_time` sono UNA decisione di
    ribilanciamento (un portfolio-cycle emette l'intero blocco
    nello stesso timestamp) e vanno trattate come un singolo
    ciclo. Altrimenti la stessa finestra temporale produrrebbe N
    cicli duplicati con un ticker ciascuno.

    Esclude i BUY con `score <= 0` (un BUY a peso 0 e' un bug, non un
    target).
    """
    s1_buys = [r for r in s1_buys if float(r["score"]) > 0]
    s4_buys = [r for r in s4_buys if float(r["score"]) > 0]
    s1_sorted = sorted(s1_buys, key=lambda r: r["tick_time"])
    s4_sorted = sorted(s4_buys, key=lambda r: r["tick_time"])

    # Raggruppa S1 BUY per timestamp (un portfolio-cycle emette tutte
    # le sue decisioni nello stesso istante).
    s1_groups: list[tuple[datetime, list[dict]]] = []
    for row in s1_sorted:
        if s1_groups and s1_groups[-1][0] == row["tick_time"]:
            s1_groups[-1][1].append(row)
        else:
            s1_groups.append((row["tick_time"], [row]))

    if not s1_groups:
        return []

    cycles: list[dict] = []
    for i, (ts, s1_group) in enumerate(s1_groups):
        # Inizio della finestra: la decisione S1 precedente, o
        # `ts - cycle_window` se e' la prima.
        if i == 0:
            window_start = ts - cycle_window
        else:
            window_start = s1_groups[i - 1][0]
        window_end = ts

        s4_in_window = [
            r for r in s4_sorted if window_start < r["tick_time"] <= window_end
        ]

        w_s1 = _ticker_weights(s1_group)
        w_s4 = _ticker_weights(s4_in_window)
        s1_tickers = set(w_s1)
        s4_tickers = set(w_s4)
        cycles.append(
            {
                "s1_tick_time": ts.isoformat(),
                "s1_symbols": sorted(s1_tickers),
                "s4_symbols": sorted(s4_tickers),
                "n_s1": len(s1_tickers),
                "n_s4": len(s4_tickers),
                "jaccard": jaccard(s1_tickers, s4_tickers),
                "weight_correlation": weight_correlation(w_s1, w_s4),
            }
        )
    return cycles


# ─── Classificazione del disaccordo ──────────────────────────────────────────


def classify_disagreement(
    s1_buys_cycle: list[dict],
    s4_buys_cycle: list[dict],
    s1_sells_cycle: list[dict],
) -> dict:
    """Distingue tre forme di disaccordo nel ciclo:
      - `s4_unique`: S4 compra un ticker che S1 ignora (non ha BUY e
        non ha SELL nello stesso ciclo);
      - `s1_unique`: S1 compra un ticker che S4 ignora;
      - `s4_buys_against_s1_sells`: S4 compra un ticker che S1 sta
        vendendo nello stesso ciclo — il reversal documentato da #182.
    """
    s1_buy_set = {r["symbol"] for r in s1_buys_cycle}
    s1_sell_set = {r["symbol"] for r in s1_sells_cycle}
    s4_buy_set = {r["symbol"] for r in s4_buys_cycle}

    s4_against_sells = s4_buy_set & s1_sell_set
    s4_unique = s4_buy_set - s1_buy_set - s1_sell_set
    s1_unique = s1_buy_set - s4_buy_set
    return {
        "s4_unique": sorted(s4_unique),
        "s1_unique": sorted(s1_unique),
        "s4_buys_against_s1_sells": sorted(s4_against_sells),
    }


# ─── Driver: legge DB, calcola, scrive evidence ─────────────────────────────


def _s1_sells_in_cycle(
    s1_sells_all: list[dict], s1_buys: list[dict], cycle_window: timedelta
) -> list[list[dict]]:
    """Per ogni ciclo (definito da una S1 BUY), i SELL S1 attribuibili.

    Un SELL S1 appartiene al ciclo della BUY S1 che lo ha preceduto
    *immediatamente* — non a quello della BUY che segue, perche' la
    BUY e' la *causa* del SELL (S1 SELL dopo che S1 ha comprato = il
    segnale e' andato via). Quindi il SELL e' retroattivamente nel
    ciclo della BUY che lo ha aperto, non nel ciclo successivo.

    Allo stesso modo di `compute_per_cycle_overlap`, raggruppa le S1
    BUY per timestamp: un portfolio-cycle emette l'intero blocco
    nello stesso istante.
    """
    s1_buys_sorted = sorted(s1_buys, key=lambda r: r["tick_time"])
    s1_sells_sorted = sorted(s1_sells_all, key=lambda r: r["tick_time"])
    s1_groups: list[datetime] = []
    for row in s1_buys_sorted:
        if not s1_groups or s1_groups[-1] != row["tick_time"]:
            s1_groups.append(row["tick_time"])

    out: list[list[dict]] = []
    for i, ts in enumerate(s1_groups):
        if i == 0:
            window_start = ts - cycle_window
        else:
            window_start = s1_groups[i - 1]
        window_end = ts
        out.append(
            [
                r
                for r in s1_sells_sorted
                if window_start < r["tick_time"] <= window_end
            ]
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since",
        default="2026-06-15",
        help="Inizio della finestra (default 2026-06-15, inizio della serie S4).",
    )
    parser.add_argument(
        "--cycle-window-days",
        type=int,
        default=DEFAULT_CYCLE_WINDOW.days,
        help="Ampiezza della finestra di confronto (default 30, copre la cadenza MONTHLY di S1 post-#185).",
    )
    parser.add_argument(
        "--universe",
        type=int,
        default=DEFAULT_UNIVERSE_SIZE,
        help=f"Cardinalita' dell'universo S1 per il baseline casuale (default {DEFAULT_UNIVERSE_SIZE}).",
    )
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since).astimezone(timezone.utc)
    cycle_window = timedelta(days=args.cycle_window_days)

    print(f"Lettura decisioni dal {since.isoformat()} (grana ciclo: {cycle_window.days}g)")
    all_rows = _leggi_decisioni(since)
    print(f"Lette {len(all_rows)} righe BUY/SELL")

    s1_buys, s4_buys = split_by_sleeve(all_rows)
    s1_sells = [r for r in all_rows if r["decision"] == "SELL" and (r.get("reason") or "").startswith("S1")]

    print(f"  BUY S1: {len(s1_buys)} | BUY S4: {len(s4_buys)} | SELL S1: {len(s1_sells)}")

    cycles = compute_per_cycle_overlap(s1_buys, s4_buys, cycle_window)
    s1_sells_per_cycle = _s1_sells_in_cycle(s1_sells, s1_buys, cycle_window)

    # Classificazione del disaccordo per ogni ciclo.
    disagreement: list[dict] = []
    for cycle, s1_sells_cycle in zip(cycles, s1_sells_per_cycle):
        s1_buys_cycle = [
            {"symbol": s, "tick_time": datetime.fromisoformat(cycle["s1_tick_time"])}
            for s in cycle["s1_symbols"]
        ]
        s4_buys_cycle = [
            {"symbol": s, "tick_time": datetime.fromisoformat(cycle["s1_tick_time"])}
            for s in cycle["s4_symbols"]
        ]
        cls = classify_disagreement(s1_buys_cycle, s4_buys_cycle, s1_sells_cycle)
        disagreement.append(
            {
                "s1_tick_time": cycle["s1_tick_time"],
                "s4_unique_count": len(cls["s4_unique"]),
                "s1_unique_count": len(cls["s1_unique"]),
                "reversal_count": len(cls["s4_buys_against_s1_sells"]),
                "s4_unique_symbols": cls["s4_unique"],
                "s1_unique_symbols": cls["s1_unique"],
                "reversal_symbols": cls["s4_buys_against_s1_sells"],
            }
        )

    # Sintesi: media e mediana delle Jaccard, conteggio reversal.
    if cycles:
        jaccards = [c["jaccard"] for c in cycles]
        corrs = [c["weight_correlation"] for c in cycles]
        n_s1_means = sum(c["n_s1"] for c in cycles) / len(cycles)
        n_s4_means = sum(c["n_s4"] for c in cycles) / len(cycles)
        summary = {
            "n_cycles": len(cycles),
            "jaccard_mean": sum(jaccards) / len(jaccards),
            "jaccard_max": max(jaccards),
            "jaccard_min": min(jaccards),
            "weight_corr_mean": sum(corrs) / len(corrs),
            "n_s1_mean_per_cycle": n_s1_means,
            "n_s4_mean_per_cycle": n_s4_means,
            "expected_jaccard_random": expected_jaccard_random_baseline(
                args.universe, n_s1_means, n_s4_means
            ),
            "reversal_count_total": sum(d["reversal_count"] for d in disagreement),
        }
    else:
        summary = {
            "n_cycles": 0,
            "jaccard_mean": None,
            "jaccard_max": None,
            "jaccard_min": None,
            "weight_corr_mean": None,
            "n_s1_mean_per_cycle": 0,
            "n_s4_mean_per_cycle": 0,
            "expected_jaccard_random": None,
            "reversal_count_total": 0,
        }

    out_payload = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "finestra_letta": {
            "since": since.isoformat(),
            "cycle_window_days": cycle_window.days,
        },
        "metodo": {
            "attribuzione": "Colonna `reason` di execution_decisions: 'S1 momentum:' o 'S4 news-driven:' o 'S4+S1'. Mai basata solo su signal_id (i BUY S1 non hanno signal_id).",
            "granularita_ciclo": "Una S1 BUY = un ciclo. Le S4 BUY nella finestra (S1 precedente, S1 corrente] entrano in quel ciclo.",
            "soglia_buy": "score > 0 (un BUY a peso 0 e' escluso come bug, non come target).",
        },
        "attribuzione_righe": {
            "buy_s1": len(s1_buys),
            "buy_s4": len(s4_buys),
            "sell_s1": len(s1_sells),
            "totale_lette": len(all_rows),
        },
        "riepilogo": summary,
        "serie_per_ciclo": cycles,
        "disaccordo_per_ciclo": disagreement,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_payload, indent=2, default=str))
    print(f"Scritto {OUT}")
    print()
    print(f"Cicli di confronto: {summary['n_cycles']}")
    if summary["n_cycles"] > 0:
        print(
            f"Jaccard media = {summary['jaccard_mean']:.3f}  "
            f"(min {summary['jaccard_min']:.3f}, max {summary['jaccard_max']:.3f})"
        )
        print(
            f"Correlazione pesi media = {summary['weight_corr_mean']:.3f}"
        )
        print(
            f"|S1| medio = {summary['n_s1_mean_per_cycle']:.1f}, "
            f"|S4| medio = {summary['n_s4_mean_per_cycle']:.1f}, "
            f"baseline casuale = {summary['expected_jaccard_random']:.3f}"
        )
        print(
            f"Reversal S4 BUY vs S1 SELL (coda #182): {summary['reversal_count_total']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
