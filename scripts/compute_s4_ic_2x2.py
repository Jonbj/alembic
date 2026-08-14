#!/usr/bin/env python3
"""IC di S4 scomposto 2x2: {ensemble, fallback} x {|score|>=gate, <gate}.

Perche' esiste. `s4_ic.json` riporta una riga `alta_convinzione_0.30` che mescola
segnali ensemble e segnali FinBERT-fallback. Quattro analisi indipendenti sulla
decisione dell'orizzonte di S4 (docs/s4-orizzonte-review-2026-08-13/) hanno
ragionato su quella riga, e una di esse ha costruito la propria raccomandazione
sulla sua forma monotona crescente (+0.0434 -> +0.0465 -> +0.0624 a 1/3/5 giorni),
letta come "l'alpha cresce con l'orizzonte". Nessuna ha potuto verificare se la
monotonia fosse un artefatto della miscela, perche' la scomposizione non esisteva.

Questo script la produce. Sola lettura sul DB, idempotente: ricalcola tutto ogni
volta e riscrive l'output, quindi non puo' divergere da cio' che il DB dice oggi.

METODO — identico a compute_s4_ic.py, deliberatamente.
Una osservazione per simbolo-giorno tenendo l'ULTIMO segnale del giorno (e'
quello che il ranker usa in produzione), Spearman cross-sectional per giorno,
media e t sui giorni. MIN_SIMBOLI_GIORNO = 5 come nello script principale.

IL PUNTO DELLO SCRIPT NON E' IL NUMERO PRIMARIO, E' LA SUA INSTABILITA'.
La sezione `sensibilita_min_simboli` fa variare l'unico parametro arbitrario del
calcolo. Con questo campione la FORMA della struttura a termine si capovolge:
soglia bassa -> picco a 1 giorno, soglia alta -> picco a 3-5 giorni. Un protocollo
di misura pre-registrato deve fissare questo parametro PRIMA di guardare i
risultati, altrimenti i dati rispondono quello che gli si chiede.

Uso:
    uv run python scripts/compute_s4_ic_2x2.py
"""
from __future__ import annotations

import json
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import spearmanr

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT = PROJECT_DIR / "docs" / "evidence" / "s4_ic_2x2.json"

# Stessa convenzione di compute_s4_ic.py: sotto i 5 simboli la correlazione
# cross-sectional del giorno e' rumore puro.
MIN_SIMBOLI_GIORNO = 5
# Soglia d'ordine di S4 (feedback:entry_threshold baseline). Non letta da Redis:
# questo script ricostruisce la storia, e la soglia del giorno e' irrilevante per
# la domanda "la riga alta-convinzione e' contaminata".
GATE = 0.30
# Il ventaglio di sensibilita'. 5 e' il valore di produzione ed e' incluso.
SOGLIE_SENSIBILITA = (3, 5, 8, 10, 15)

ORIZZONTI = (("1g", "forward_return"), ("3g", "forward_return_3d"), ("5g", "forward_return_5d"))

QUERY = """
SELECT DISTINCT ON (symbol, generated_at::date)
  generated_at::date, symbol, score, fallback_used,
  forward_return, forward_return_3d, forward_return_5d
FROM sentiment_signals
WHERE forward_return IS NOT NULL
ORDER BY symbol, generated_at::date, generated_at DESC;
"""


def _psql(query: str) -> list[list[str]]:
    """Query read-only su Postgres. Righe come liste di stringhe."""
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:300]}")
    return [r.split("|") for r in res.stdout.strip().split("\n") if r.strip()]


def _carica() -> list[dict]:
    righe: list[dict] = []
    for p in _psql(QUERY):
        try:
            righe.append({
                "giorno": p[0],
                "symbol": p[1],
                "score": float(p[2]),
                "fallback": p[3] == "t",
                "forward_return": float(p[4]) if p[4] else None,
                "forward_return_3d": float(p[5]) if p[5] else None,
                "forward_return_5d": float(p[6]) if p[6] else None,
            })
        except (ValueError, IndexError):
            # Riga malformata: si scarta, non si indovina un valore.
            continue
    return righe


def _ic(righe: list[dict], filtro, campo: str, min_simboli: int) -> dict | None:
    """IC medio, t e numerosita' per una cella. None se meno di 5 giorni utili."""
    per_giorno: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in righe:
        fw = r[campo]
        if fw is None or not filtro(r):
            continue
        per_giorno[r["giorno"]].append((r["score"], fw))

    ics: list[float] = []
    osservazioni = 0
    for valori in per_giorno.values():
        if len(valori) < min_simboli:
            continue
        rho = spearmanr([v[0] for v in valori], [v[1] for v in valori]).statistic
        if rho == rho:  # scarta NaN (score tutti uguali nel giorno)
            ics.append(float(rho))
            osservazioni += len(valori)

    if len(ics) < 5:
        return None
    media = statistics.mean(ics)
    dev = statistics.stdev(ics)
    t = media / (dev / len(ics) ** 0.5) if dev > 0 else 0.0
    return {
        "ic_medio": media,
        "dev_std": dev,
        "t_stat": t,
        "giorni": len(ics),
        "osservazioni": osservazioni,
    }


CELLE = {
    "ensemble_alta_convinzione": lambda r: (not r["fallback"]) and abs(r["score"]) >= GATE,
    "ensemble_sotto_gate": lambda r: (not r["fallback"]) and abs(r["score"]) < GATE,
    "fallback_alta_convinzione": lambda r: r["fallback"] and abs(r["score"]) >= GATE,
    "fallback_sotto_gate": lambda r: r["fallback"] and abs(r["score"]) < GATE,
    # La riga che s4_ic.json chiama `alta_convinzione_0.30`: le due popolazioni
    # sopra il gate, mescolate. Ricostruita qui per rendere visibile la miscela.
    "mista_alta_convinzione": lambda r: abs(r["score"]) >= GATE,
}


def costruisci() -> dict:
    righe = _carica()
    if not righe:
        raise SystemExit("Nessun segnale con forward_return: niente da calcolare.")

    scomposizione = {
        nome: {
            etichetta: _ic(righe, filtro, campo, MIN_SIMBOLI_GIORNO)
            for etichetta, campo in ORIZZONTI
        }
        for nome, filtro in CELLE.items()
    }

    sensibilita = {
        str(soglia): {
            etichetta: _ic(righe, CELLE["ensemble_alta_convinzione"], campo, soglia)
            for etichetta, campo in ORIZZONTI
        }
        for soglia in SOGLIE_SENSIBILITA
    }

    return {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "metodo": (
            "una osservazione per simbolo-giorno (ultimo segnale, come il ranker); "
            f"Spearman cross-sectional giornaliero; t sui giorni; "
            f"min {MIN_SIMBOLI_GIORNO} simboli/giorno; gate |score| >= {GATE}"
        ),
        "osservazioni_simbolo_giorno": len(righe),
        "avvertenza": (
            "La scomposizione risponde a UNA domanda: la riga alta-convinzione di "
            "s4_ic.json e' una miscela di due popolazioni con segno opposto a 1g e 3g. "
            "NON stabilisce la forma della struttura a termine dell'ensemble: vedi "
            "sensibilita_min_simboli, dove la forma si capovolge al variare dell'unico "
            "parametro arbitrario. Nessuno di questi numeri e' significativo, e sono "
            "calcolati su dati pre-fix (resolver, fan-out, copertura)."
        ),
        "scomposizione_2x2": scomposizione,
        "sensibilita_min_simboli": sensibilita,
    }


def main() -> None:
    dossier = costruisci()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dossier, indent=1, ensure_ascii=False) + "\n")

    print(f"scritto {OUT.relative_to(PROJECT_DIR)}")
    print(f"\nScomposizione 2x2 (min {MIN_SIMBOLI_GIORNO} simboli/giorno, gate {GATE}):")
    print(f"{'cella':30} {'1g':>18} {'3g':>18} {'5g':>18}  gg")
    for nome, per_orizzonte in dossier["scomposizione_2x2"].items():
        celle = []
        for etichetta, _ in ORIZZONTI:
            r = per_orizzonte[etichetta]
            celle.append(f"{r['ic_medio']:+.4f} (t{r['t_stat']:+.2f})" if r else "n/d")
        gg = per_orizzonte["1g"]["giorni"] if per_orizzonte["1g"] else 0
        print(f"{nome:30} {celle[0]:>18} {celle[1]:>18} {celle[2]:>18} {gg:3}")

    print("\nSensibilita' al minimo simboli/giorno — ensemble alta convinzione:")
    print(f"{'min':>5} {'1g':>18} {'3g':>18} {'5g':>18}  gg")
    for soglia, per_orizzonte in dossier["sensibilita_min_simboli"].items():
        celle = []
        for etichetta, _ in ORIZZONTI:
            r = per_orizzonte[etichetta]
            celle.append(f"{r['ic_medio']:+.4f} (t{r['t_stat']:+.2f})" if r else "n/d")
        gg = per_orizzonte["1g"]["giorni"] if per_orizzonte["1g"] else 0
        print(f"{soglia:>5} {celle[0]:>18} {celle[1]:>18} {celle[2]:>18} {gg:3}")


if __name__ == "__main__":
    main()
