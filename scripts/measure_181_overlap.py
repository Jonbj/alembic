#!/usr/bin/env python3
"""Misura l'overlap S1∩S4 sui target per ciclo di portfolio (issue #181).

L'overlap S1∩S4 e' la firma che distingue "S4 conferma S1" (overlap basso
e indipendente, S4 aggiunge informazione) da "S4 duplica S1" (overlap
alto, l'overlay non e' incrementale). L'audit strategie del 2026-08-04
(PI-2 in `docs/audits/strategies/PORTFOLIO_INTERACTIONS.md`) l'aveva
lasciata come TODO. La issue #181 chiede la misura.

L'oggetto misurato e' il **target** di ogni sleeve ad ogni ciclo di
portfolio, non l'evento di ingresso:

    target(sleeve, ciclo) = posizioni aperte attribuite alla sleeve
                          ∪ intenti di ingresso della sleeve in quel ciclo
                          − simboli che la sleeve sta uscendo in quel ciclo

La distinzione non e' formale. Un ticker che entrambe le sleeve vogliono
tenere **non produce alcun BUY** dopo il primo ingresso: il guard
anti-pyramiding (P0-05, `portfolio_scheduler.py`) scarta l'ordine perche'
la posizione e' gia' a libro. Misurare la coincidenza dei BUY misura
quindi il *complemento* dell'overlap — per costruzione ne trova ~zero.
Gli intenti bloccati sono osservabili solo dal 2026-08-11 (#231, righe
`SKIP_PYRAMIDING`): prima di quella data la censura e' totale e non
recuperabile senza reimplementare il gate di ingresso. Il riepilogo
riporta la censura esplicitamente (`censura_anti_pyramiding`), perche'
senza quel numero la serie principale si legge al contrario.

L'output e' evidenza per la decisione su S4 (ridurre a shadow, rimuovere,
oppure tenere perche' aggiunge info). NON e' un test, NON ha soglia
pre-registrata, e non cambia taratura: la finestra di osservazione
(2026-08-03 → 2026-09-28, issue #171) congela qualunque modifica.

Vincoli espliciti:
  - attribuzione S1/S4 dalla colonna `reason`, MAI da `signal_id` da solo
    (i BUY S1 non hanno signal_id; filtrare per la sua presenza
    scarterebbe il core del book). L'attribuzione e' verificata, non
    assunta: il JSON riporta il conteggio per ogni forma di `reason`
    riconosciuta e la lista di quelle non attribuibili;
  - il ciclo e' il ciclo di portfolio vero (`portfolio_cycles`), non una
    finestra inventata: le due sleeve hanno cadenze diverse (S4 15 min,
    S1 MONTHLY post-#185) ma i loro *target* esistono ad ogni ciclo;
  - la serie e' temporale, mai un singolo aggregato (la media nasconde
    se l'overlap e' strutturale o episodico);
  - il baseline atteso da selezione casuale serve a dire se il numero
    e' "tanto" o "niente" (con sleeve di dimensioni molto diverse, un
    overlap piccolo puo' essere gia' sopra il caso);
  - il caso reversal (S4 tiene a target cio' che S1 sta vendendo, coda
    #182) e' separato dal "S4 compra cio' che S1 ignora": piu' grave
    della semplice ridondanza, e' la causa documentata della perdita
    −$83.86 del 2026-07-16.

Output: serie per ciclo di portfolio, scritta in
`docs/evidence/s1_s4_overlap.json`. Idempotente: ricalcola l'intera
serie ad ogni run, non accumula stato. Sola lettura sul DB.

Uso:
    uv run python scripts/measure_181_overlap.py
    uv run python scripts/measure_181_overlap.py --since 2026-06-15
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
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

# Le righe di decisione non portano il timestamp del ciclo ma quello della
# loro scrittura, che cade qualche secondo dopo (le righe SKIP_PYRAMIDING
# sono scritte a fine ciclo, #231). Una decisione appartiene all'ultimo
# ciclo che la precede, entro questa tolleranza.
CYCLE_MATCH_TOLERANCE = timedelta(minutes=20)

# Le righe che registrano un intento di ingresso: il BUY effettivo e il
# BUY fermato dal guard anti-pyramiding (#231). Entrambe dicono "questa
# sleeve vuole il ticker a target"; solo la prima diventa un ordine.
ENTRY_DECISIONS = ("BUY", "SKIP_PYRAMIDING")

# Dalla data in cui #231 registra i BUY fermati dal guard: prima, gli
# intenti di ingresso su nomi gia' a libro non lasciano alcuna riga.
UNCENSORED_SINCE = datetime(2026, 8, 11, tzinfo=timezone.utc)


# ─── I/O DB: docker exec psql, stessa firma di compute_s4_ic.py ─────────────


# `reason` e' testo libero: sta in ultima posizione in ogni SELECT cosi'
# un'eventuale pipe al suo interno non sfasa le colonne (split con maxsplit).
QUERY_CYCLES = """\
SELECT timestamp
FROM portfolio_cycles
WHERE timestamp >= '{since}'
ORDER BY timestamp;"""

QUERY_DECISIONS = """\
SELECT tick_time, symbol, decision, score, coalesce(signal_score::text, ''), reason
FROM execution_decisions
WHERE decision IN ('BUY', 'SELL', 'SKIP_PYRAMIDING')
  AND tick_time >= '{since}'
ORDER BY tick_time;"""

# Le posizioni aperte sono la parte di target che nessun BUY ripete: un
# ticker gia' a libro resta il target della sua sleeve finche' non esce.
# L'attribuzione passa dalla decisione che ha aperto il trade.
QUERY_POSITIONS = """\
SELECT t.entry_time, coalesce(t.exit_time::text, ''), t.symbol, coalesce(d.score, 0), coalesce(d.reason, '')
FROM trades t
LEFT JOIN execution_decisions d ON d.id = t.decision_id
WHERE t.exit_time IS NULL OR t.exit_time >= '{since}'
ORDER BY t.entry_time;"""


def _psql(sql: str) -> str:
    cmd = [
        "docker", "exec", "alembic-postgres-1", "psql",
        "-U", "trading", "-d", "trading",
        "-t", "-A", "-F", "|",
        "-c", sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:300]}")
    return res.stdout


def _rows(raw: str, n_fields: int) -> list[list[str]]:
    """Righe psql `-t -A -F|` in liste di campi; l'ultimo assorbe le pipe."""
    out: list[list[str]] = []
    for riga in raw.splitlines():
        if not riga.strip():
            continue
        parts = riga.split("|", n_fields - 1)
        if len(parts) < n_fields:
            continue
        out.append(parts)
    return out


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def leggi_cicli(since: datetime) -> list[datetime]:
    return [_dt(r[0]) for r in _rows(_psql(QUERY_CYCLES.format(since=since.isoformat())), 1)]


def leggi_decisioni(since: datetime) -> list[dict]:
    out: list[dict] = []
    for tick, symbol, decision, score, signal_score, reason in _rows(
        _psql(QUERY_DECISIONS.format(since=since.isoformat())), 6
    ):
        out.append(
            {
                "tick_time": _dt(tick),
                "symbol": symbol,
                "decision": decision,
                "score": float(score) if score else 0.0,
                "signal_score": float(signal_score) if signal_score else None,
                "reason": reason,
            }
        )
    return out


def leggi_posizioni(since: datetime) -> list[dict]:
    out: list[dict] = []
    for entry, exit_, symbol, score, reason in _rows(
        _psql(QUERY_POSITIONS.format(since=since.isoformat())), 5
    ):
        out.append(
            {
                "symbol": symbol,
                "entry_time": _dt(entry),
                "exit_time": _dt(exit_) if exit_ else None,
                "score": float(score) if score else 0.0,
                "reason": reason,
            }
        )
    return out


# ─── Attribuzione S1/S4 ──────────────────────────────────────────────────────


# Il marcatore di sleeve compare in `reason` come token isolato: "S1
# momentum:", "S4 news-driven:", "S4+S1 news-driven:", "[s1_weight_drop]
# S1 target weight dropped", "[expired] S4 signal expired". Il lookaround
# evita di pescare un ticker che contenga la sigla.
_S1_MARK = re.compile(r"(?<![A-Za-z0-9])s1(?![A-Za-z0-9])", re.IGNORECASE)
_S4_MARK = re.compile(r"(?<![A-Za-z0-9])s4(?![A-Za-z0-9])", re.IGNORECASE)


def sleeves_of_reason(reason: str) -> frozenset[str]:
    """Sleeve a cui una riga e' attribuibile, dalla sola colonna `reason`.

    Riconosce ogni forma prodotta da `portfolio_scheduler.py`, non solo i
    prefissi di ingresso:
      - `S1 momentum: ...`                      → {S1}
      - `S4 news-driven: ...`                   → {S4}
      - `S4+S1 news-driven: ...`                → {S1, S4}
      - `[s1_weight_drop] S1 target weight ...` → {S1}
      - `[expired] S4 signal expired ...`       → {S4}
      - `[whipsaw] Portfolio rebalance ... S4 signal present ...` → {S4}
      - `Portfolio rebalance: weight 0.0%.`     → ∅ (nessuna sleeve nel testo)
      - `stop_loss: MRK px 121.3 ...`           → ∅ (uscita di rischio)

    Le righe ∅ non sono attribuibili e restano fuori dal conteggio: il
    JSON di output le elenca con i loro conteggi, cosi' l'attribuzione e'
    verificabile invece che assunta (DoD #181).
    """
    reason = reason or ""
    sleeves = set()
    if _S1_MARK.search(reason):
        sleeves.add("S1")
    if _S4_MARK.search(reason):
        sleeves.add("S4")
    return frozenset(sleeves)


def sleeves_of_row(row: dict) -> frozenset[str]:
    """Sleeve di una riga di decisione, `reason` per prima.

    Le righe `SKIP_PYRAMIDING` (#231) fanno eccezione: il loro `reason`
    (`"P0-05 anti-pyramiding: gia' a libro dal ..., sentiment +0.396,
    peso non allocato 2.3%"`) non nomina la sleeve. Il marcatore c'e'
    lo stesso ed e' strutturale, non testuale: `signal_score` viene
    valorizzato solo quando l'ordine bloccato portava il tag S4
    (`portfolio_scheduler.py`, `signal_score=... if "S4" in strats else
    None`). Un blocco senza `signal_score` viene dall'unica altra sleeve
    viva, S1.

    Scartare queste righe per mancanza di prefisso significherebbe
    perdere l'unica traccia esistente degli ingressi che il guard ferma —
    cioe' proprio i casi in cui le due sleeve vogliono lo stesso ticker.
    """
    dal_testo = sleeves_of_reason(row.get("reason") or "")
    if dal_testo:
        return dal_testo
    if row.get("decision") == "SKIP_PYRAMIDING":
        return frozenset({"S4"}) if row.get("signal_score") is not None else frozenset({"S1"})
    return frozenset()


def split_by_sleeve(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Separa gli **eventi di ingresso** in S1 e S4 (misura secondaria).

    Serve alla coincidenza degli eventi di ingresso, che e' cosa diversa
    dall'overlap dei target: un ticker che entrambe le sleeve vogliono
    tenere non produce un secondo BUY (guard anti-pyramiding). Tenuta
    perche' la coincidenza degli ingressi dice qualcosa sul churn, non
    perche' risponda alla domanda della issue.

    I BUY con `signal_id IS NULL` non sono per forza S1 — la colonna
    `reason` e' l'unica fonte affidabile. Filtrare per `signal_id`
    scarterebbe i BUY S1.
    """
    s1: list[dict] = []
    s4: list[dict] = []
    for row in rows:
        if row["decision"] not in ENTRY_DECISIONS:
            continue
        sleeves = sleeves_of_row(row)
        if "S1" in sleeves:
            s1.append(row)
        if "S4" in sleeves:
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


def assign_to_cycle(
    ts: datetime,
    cycles: list[datetime],
    tolerance: timedelta = CYCLE_MATCH_TOLERANCE,
) -> datetime | None:
    """Ciclo di portfolio a cui appartiene una riga scritta a `ts`.

    Una decisione e' scritta qualche secondo dopo il ciclo che l'ha
    prodotta (le righe SKIP_PYRAMIDING anche a fine ciclo, #231), mai
    prima: il ciclo giusto e' l'ultimo che precede `ts`. Oltre la
    tolleranza la riga non appartiene ad alcun ciclo — succede quando il
    ciclo non e' stato persistito o la riga viene da un altro percorso
    (es. `run-execution`), e in quel caso la riga viene scartata invece
    di essere attribuita al ciclo sbagliato.
    """
    if not cycles:
        return None
    idx = bisect.bisect_right(cycles, ts) - 1
    if idx < 0:
        return None
    candidato = cycles[idx]
    if ts - candidato > tolerance:
        return None
    return candidato


# ─── Misura per ciclo: target, non eventi ───────────────────────────────────


def compute_target_overlap_per_cycle(
    cycles: list[datetime],
    positions: list[dict],
    decisions: list[dict],
    universe_size: int = DEFAULT_UNIVERSE_SIZE,
    tolerance: timedelta = CYCLE_MATCH_TOLERANCE,
) -> list[dict]:
    """Serie per ciclo di portfolio dell'overlap fra i target S1 e S4.

    Il target di una sleeve ad un ciclo e':
      posizioni aperte attribuite alla sleeve
      ∪ intenti di ingresso della sleeve in quel ciclo (BUY, SKIP_PYRAMIDING)
      − simboli in uscita per quella sleeve in quel ciclo (SELL attribuito)

    Il peso di un simbolo e' l'ultimo peso target visto per quella sleeve
    (dall'intento piu' recente, altrimenti dal peso di ingresso della
    posizione). I pesi servono alla correlazione, non alla Jaccard.

    `positions` e `decisions` sono liste di dict cosi' come le
    restituiscono `leggi_posizioni` / `leggi_decisioni`; la funzione non
    tocca il DB ed e' testabile con dati sintetici.
    """
    cycles = sorted(cycles)
    if not cycles:
        return []

    # Intenti e uscite raggruppati per ciclo, cosi' l'iterazione sotto e'
    # lineare invece che quadratica.
    intents_by_cycle: dict[datetime, list[dict]] = defaultdict(list)
    exits_by_cycle: dict[datetime, list[dict]] = defaultdict(list)
    for row in decisions:
        sleeves = sleeves_of_row(row)
        if not sleeves:
            continue
        cycle = assign_to_cycle(row["tick_time"], cycles, tolerance)
        if cycle is None:
            continue
        entry = {"symbol": row["symbol"], "sleeves": sleeves, "score": float(row["score"])}
        if row["decision"] in ENTRY_DECISIONS:
            intents_by_cycle[cycle].append(entry)
        elif row["decision"] == "SELL":
            exits_by_cycle[cycle].append(entry)

    posizioni = [
        {
            "symbol": p["symbol"],
            "entry_time": p["entry_time"],
            "exit_time": p["exit_time"],
            "score": float(p["score"]),
            "sleeves": sleeves_of_reason(p.get("reason") or ""),
        }
        for p in positions
    ]

    # Ultimo peso target noto per (sleeve, simbolo); aggiornato dagli
    # intenti man mano che la serie avanza.
    ultimo_peso: dict[tuple[str, str], float] = {}

    serie: list[dict] = []
    for ts in cycles:
        for intento in intents_by_cycle.get(ts, ()):
            for sleeve in intento["sleeves"]:
                ultimo_peso[(sleeve, intento["symbol"])] = intento["score"]

        target: dict[str, dict[str, float]] = {"S1": {}, "S4": {}}
        for pos in posizioni:
            if pos["entry_time"] > ts:
                continue
            if pos["exit_time"] is not None and pos["exit_time"] <= ts:
                continue
            for sleeve in pos["sleeves"]:
                target[sleeve][pos["symbol"]] = ultimo_peso.get(
                    (sleeve, pos["symbol"]), pos["score"]
                )
        for intento in intents_by_cycle.get(ts, ()):
            for sleeve in intento["sleeves"]:
                target[sleeve][intento["symbol"]] = intento["score"]

        uscite: dict[str, set[str]] = {"S1": set(), "S4": set()}
        for uscita in exits_by_cycle.get(ts, ()):
            for sleeve in uscita["sleeves"]:
                uscite[sleeve].add(uscita["symbol"])
                target[sleeve].pop(uscita["symbol"], None)

        s1_set = set(target["S1"])
        s4_set = set(target["S4"])
        disaccordo = classify_disagreement(s1_set, s4_set, uscite["S1"])
        serie.append(
            {
                "cycle_ts": ts.isoformat(),
                "s1_symbols": sorted(s1_set),
                "s4_symbols": sorted(s4_set),
                "n_s1": len(s1_set),
                "n_s4": len(s4_set),
                "n_intersezione": len(s1_set & s4_set),
                "intersezione": sorted(s1_set & s4_set),
                "jaccard": jaccard(s1_set, s4_set),
                "jaccard_baseline_casuale": expected_jaccard_random_baseline(
                    universe_size, len(s1_set), len(s4_set)
                ),
                # Con sleeve di dimensioni molto diverse (S1 decine di nomi,
                # S4 pochi) la Jaccard e' schiacciata dal denominatore: la
                # domanda "S4 duplica S1?" si legge meglio come "quanta parte
                # del target S4 sta gia' nel book S1?". Il caso di riferimento
                # e' |S1|/universo — la quota che una scelta casuale colpirebbe.
                "quota_s4_dentro_s1": (
                    len(s1_set & s4_set) / len(s4_set) if s4_set else None
                ),
                "quota_s4_dentro_s1_baseline_casuale": (
                    len(s1_set) / universe_size if universe_size else None
                ),
                "weight_correlation": weight_correlation(target["S1"], target["S4"]),
                "s4_unique_count": len(disaccordo["s4_unique"]),
                "s1_unique_count": len(disaccordo["s1_unique"]),
                "reversal_count": len(disaccordo["s4_targets_against_s1_exits"]),
                "reversal_symbols": disaccordo["s4_targets_against_s1_exits"],
            }
        )
    return serie


# ─── Classificazione del disaccordo ──────────────────────────────────────────


def classify_disagreement(
    s1_targets: Iterable[str],
    s4_targets: Iterable[str],
    s1_exits: Iterable[str],
) -> dict:
    """Distingue tre forme di disaccordo nel ciclo:
      - `s4_unique`: S4 tiene a target un ticker che S1 ignora;
      - `s1_unique`: S1 tiene a target un ticker che S4 ignora;
      - `s4_targets_against_s1_exits`: S4 tiene a target un ticker che S1
        sta uscendo nello stesso ciclo — il reversal documentato da #182,
        piu' grave della semplice ridondanza.
    """
    s1_set = set(s1_targets)
    s4_set = set(s4_targets)
    exit_set = set(s1_exits)

    contro_uscite = s4_set & exit_set
    return {
        "s4_unique": sorted(s4_set - s1_set - exit_set),
        "s1_unique": sorted(s1_set - s4_set),
        "s4_targets_against_s1_exits": sorted(contro_uscite),
    }


# ─── Censura del guard anti-pyramiding ──────────────────────────────────────


def anti_pyramiding_censoring(
    decisions: list[dict],
    positions: list[dict],
    since: datetime = UNCENSORED_SINCE,
) -> dict:
    """Quanto della coincidenza fra le sleeve e' invisibile agli eventi.

    Un BUY S4 su un ticker gia' a libro non diventa mai una riga BUY: il
    guard P0-05 lo scarta. Dal 2026-08-11 (#231) resta una riga
    `SKIP_PYRAMIDING`, e su quella finestra si puo' contare quanti degli
    intenti di ingresso di S4 cadevano su nomi che S1 gia' teneva. Prima
    di quella data il conteggio non e' ricostruibile dalle decisioni.

    Ritorna i conteggi grezzi: intenti S4 totali, intenti fermati dal
    guard, e quanti di essi su nomi in quel momento a libro per S1.
    """
    intenti = [
        row
        for row in decisions
        if row["decision"] in ENTRY_DECISIONS
        and row["tick_time"] >= since
        and "S4" in sleeves_of_row(row)
    ]
    posizioni_s1 = [
        p
        for p in positions
        if "S1" in sleeves_of_reason(p.get("reason") or "")
    ]

    def _in_book_s1(symbol: str, ts: datetime) -> bool:
        for p in posizioni_s1:
            if p["symbol"] != symbol:
                continue
            if p["entry_time"] > ts:
                continue
            if p["exit_time"] is not None and p["exit_time"] <= ts:
                continue
            return True
        return False

    bloccati = [r for r in intenti if r["decision"] == "SKIP_PYRAMIDING"]
    su_nomi_s1 = [r for r in intenti if _in_book_s1(r["symbol"], r["tick_time"])]
    return {
        "finestra_non_censurata_da": since.isoformat(),
        "intenti_ingresso_s4": len(intenti),
        "intenti_fermati_dal_guard": len(bloccati),
        "intenti_su_nomi_gia_a_libro_s1": len(su_nomi_s1),
        "quota_intenti_su_nomi_s1": (
            len(su_nomi_s1) / len(intenti) if intenti else None
        ),
        "simboli": sorted({r["symbol"] for r in su_nomi_s1}),
    }


# ─── Verifica dell'attribuzione ──────────────────────────────────────────────


def attribution_audit(decisions: list[dict], positions: list[dict]) -> dict:
    """Conteggi per forma di `reason`, incluse quelle non attribuibili.

    La DoD della issue chiede che l'attribuzione sia verificata e non
    assunta: questo blocco finisce nel JSON di output, cosi' chi legge la
    misura vede quante righe sono state assegnate a S1, a S4, a entrambe,
    e quante sono rimaste fuori (con il testo che le ha fatte scartare).
    """
    conteggi: dict[str, int] = defaultdict(int)
    non_attribuite: dict[str, int] = defaultdict(int)
    for row in list(decisions) + list(positions):
        reason = row.get("reason") or ""
        sleeves = sleeves_of_row(row)
        if not sleeves:
            non_attribuite[reason[:60]] += 1
            conteggi["nessuna"] += 1
        elif sleeves == frozenset({"S1", "S4"}):
            conteggi["S1+S4"] += 1
        else:
            conteggi[next(iter(sleeves))] += 1
    return {
        "righe_per_sleeve": dict(conteggi),
        "reason_non_attribuibili": dict(
            sorted(non_attribuite.items(), key=lambda kv: -kv[1])[:20]
        ),
    }


# ─── Driver: legge DB, calcola, scrive evidence ─────────────────────────────


def _mediana(valori: list[float]) -> float | None:
    if not valori:
        return None
    ordinati = sorted(valori)
    meta = len(ordinati) // 2
    if len(ordinati) % 2:
        return ordinati[meta]
    return (ordinati[meta - 1] + ordinati[meta]) / 2


def riepiloga(serie: list[dict], universe_size: int) -> dict:
    """Sintesi della serie. I cicli con entrambe le sleeve vuote restano
    fuori dalle medie (la Jaccard del vuoto e' 1 per convenzione e
    gonfierebbe il numero senza dire nulla)."""
    utili = [c for c in serie if c["n_s1"] or c["n_s4"]]
    if not utili:
        return {"n_cicli": len(serie), "n_cicli_con_target": 0}
    jaccards = [c["jaccard"] for c in utili]
    con_overlap = [c for c in utili if c["n_intersezione"] > 0]
    n_s1 = sum(c["n_s1"] for c in utili) / len(utili)
    n_s4 = sum(c["n_s4"] for c in utili) / len(utili)
    con_s4 = [c for c in utili if c["n_s4"] > 0]
    quote = [c["quota_s4_dentro_s1"] for c in con_s4]
    quote_baseline = [c["quota_s4_dentro_s1_baseline_casuale"] for c in con_s4]
    return {
        "n_cicli": len(serie),
        "n_cicli_con_target": len(utili),
        "jaccard_media": sum(jaccards) / len(jaccards),
        "jaccard_mediana": _mediana(jaccards),
        "jaccard_max": max(jaccards),
        "jaccard_min": min(jaccards),
        "n_cicli_con_overlap": len(con_overlap),
        "quota_cicli_con_overlap": len(con_overlap) / len(utili),
        "weight_corr_media": sum(c["weight_correlation"] for c in utili) / len(utili),
        "n_s1_medio_per_ciclo": n_s1,
        "n_s4_medio_per_ciclo": n_s4,
        "jaccard_baseline_casuale": expected_jaccard_random_baseline(
            universe_size, round(n_s1), round(n_s4)
        ),
        "n_cicli_con_target_s4": len(con_s4),
        "quota_s4_dentro_s1_media": (sum(quote) / len(quote)) if quote else None,
        "quota_s4_dentro_s1_baseline_media": (
            (sum(quote_baseline) / len(quote_baseline)) if quote_baseline else None
        ),
        # Quanti cicli ogni simbolo passa nell'intersezione. Un solo nome che
        # domina la conta dice che l'overlap non viene da due selezioni che
        # convergono ma da una posizione sola: senza questo dettaglio la
        # media sembrerebbe descrivere un fenomeno diffuso.
        "intersezione_per_simbolo": dict(
            sorted(
                Counter(s for c in serie for s in c["intersezione"]).items(),
                key=lambda kv: -kv[1],
            )
        ),
        "reversal_totali": sum(c["reversal_count"] for c in serie),
        "reversal_simboli": sorted(
            {s for c in serie for s in c["reversal_symbols"]}
        ),
    }


def riepiloga_eventi(s1_buys: list[dict], s4_buys: list[dict]) -> dict:
    """Misura secondaria: coincidenza degli **eventi** di ingresso.

    Tenuta separata e dichiarata per quello che e': non risponde alla
    domanda della issue (i target), ma dice se le due sleeve entrano
    sugli stessi nomi negli stessi giorni.
    """
    per_giorno_s1: dict[str, set[str]] = defaultdict(set)
    per_giorno_s4: dict[str, set[str]] = defaultdict(set)
    for row in s1_buys:
        per_giorno_s1[row["tick_time"].date().isoformat()].add(row["symbol"])
    for row in s4_buys:
        per_giorno_s4[row["tick_time"].date().isoformat()].add(row["symbol"])
    giorni = sorted(set(per_giorno_s1) | set(per_giorno_s4))
    coincidenze = {
        g: sorted(per_giorno_s1.get(g, set()) & per_giorno_s4.get(g, set()))
        for g in giorni
    }
    return {
        "eventi_ingresso_s1": len(s1_buys),
        "eventi_ingresso_s4": len(s4_buys),
        "giorni_con_ingressi": len(giorni),
        "giorni_con_ingresso_sullo_stesso_ticker": sum(
            1 for v in coincidenze.values() if v
        ),
        "ticker_in_coincidenza": sorted({s for v in coincidenze.values() for s in v}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since",
        default="2026-06-15",
        help="Inizio della finestra (default 2026-06-15, inizio della serie S4).",
    )
    parser.add_argument(
        "--universe",
        type=int,
        default=DEFAULT_UNIVERSE_SIZE,
        help=f"Cardinalita' dell'universo S1 per il baseline casuale (default {DEFAULT_UNIVERSE_SIZE}).",
    )
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since).astimezone(timezone.utc)

    print(f"Lettura da {since.isoformat()}")
    cicli = leggi_cicli(since)
    decisioni = leggi_decisioni(since)
    posizioni = leggi_posizioni(since)
    print(
        f"  cicli di portfolio: {len(cicli)} | "
        f"decisioni BUY/SELL/SKIP_PYRAMIDING: {len(decisioni)} | "
        f"posizioni: {len(posizioni)}"
    )

    serie = compute_target_overlap_per_cycle(
        cicli, posizioni, decisioni, universe_size=args.universe
    )
    riepilogo = riepiloga(serie, args.universe)
    censura = anti_pyramiding_censoring(decisioni, posizioni)
    s1_buys, s4_buys = split_by_sleeve(decisioni)
    eventi = riepiloga_eventi(s1_buys, s4_buys)

    out_payload = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "finestra_letta": {"since": since.isoformat(), "universo": args.universe},
        "metodo": {
            "oggetto_misurato": (
                "Target per ciclo di portfolio: posizioni aperte attribuite alla sleeve "
                "∪ intenti di ingresso del ciclo (BUY, SKIP_PYRAMIDING) − uscite della "
                "sleeve nel ciclo. NON la coincidenza degli eventi BUY."
            ),
            "ciclo": "Timestamp di `portfolio_cycles`; ogni riga di decisione e' attribuita all'ultimo ciclo che la precede (tolleranza 20 min).",
            "attribuzione": "Colonna `reason` di execution_decisions (token isolato S1/S4, incluse le forme `[s1_weight_drop]`, `[expired] S4`, `S4+S1`). Mai basata solo su signal_id (i BUY S1 non hanno signal_id).",
            "censura": (
                "Il guard anti-pyramiding (P0-05) impedisce a una sleeve di aprire una "
                "posizione su un nome gia' a libro: l'overlap realizzato e' spinto verso "
                "zero per costruzione. Gli intenti bloccati sono osservabili solo dal "
                "2026-08-11 (#231)."
            ),
        },
        "attribuzione_verificata": attribution_audit(decisioni, posizioni),
        "riepilogo": riepilogo,
        "censura_anti_pyramiding": censura,
        "coincidenza_eventi_ingresso": eventi,
        "serie_per_ciclo": serie,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_payload, indent=2, default=str))
    print(f"Scritto {OUT}")
    print()
    print(f"Cicli di portfolio: {riepilogo['n_cicli']} (con target: {riepilogo.get('n_cicli_con_target', 0)})")
    if riepilogo.get("n_cicli_con_target"):
        print(
            f"Jaccard media = {riepilogo['jaccard_media']:.3f} "
            f"(mediana {riepilogo['jaccard_mediana']:.3f}, max {riepilogo['jaccard_max']:.3f}), "
            f"baseline casuale = {riepilogo['jaccard_baseline_casuale']:.3f}"
        )
        print(
            f"|S1| medio = {riepilogo['n_s1_medio_per_ciclo']:.1f}, "
            f"|S4| medio = {riepilogo['n_s4_medio_per_ciclo']:.1f}, "
            f"cicli con intersezione non vuota = {riepilogo['n_cicli_con_overlap']} "
            f"({riepilogo['quota_cicli_con_overlap']:.1%})"
        )
        if riepilogo["quota_s4_dentro_s1_media"] is not None:
            print(
                f"Quota del target S4 gia' nel book S1 = "
                f"{riepilogo['quota_s4_dentro_s1_media']:.1%} "
                f"(baseline casuale {riepilogo['quota_s4_dentro_s1_baseline_media']:.1%}, "
                f"su {riepilogo['n_cicli_con_target_s4']} cicli con target S4)"
            )
        print(f"Correlazione pesi media = {riepilogo['weight_corr_media']:.3f}")
        print(f"Reversal (S4 a target su cio' che S1 esce, #182): {riepilogo['reversal_totali']}")
    quota = censura["quota_intenti_su_nomi_s1"]
    print(
        f"Censura anti-pyramiding dal {censura['finestra_non_censurata_da'][:10]}: "
        f"{censura['intenti_fermati_dal_guard']}/{censura['intenti_ingresso_s4']} intenti S4 fermati dal guard, "
        f"{censura['intenti_su_nomi_gia_a_libro_s1']} su nomi gia' a libro per S1"
        + (f" ({quota:.0%})" if quota is not None else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
