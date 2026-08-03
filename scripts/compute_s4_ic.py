#!/usr/bin/env python3
"""Information Coefficient di S4: il segnale di sentiment predice i rendimenti?

Ricalcola OGNI VOLTA l'intera serie e riscrive docs/evidence/s4_ic.json. E'
idempotente per costruzione: non accumula stato, quindi non puo' divergere da
quello che il DB dice oggi. Sola lettura sul database.

Autonomo di proposito: non tocca il cron del report alpha-miss, che e' script di
produzione ed e' congelato fino alla verifica del primo commit automatico del
ledger (vedi #171, #174). Il collegamento al report arrivera' con #174.

METODO — la scelta che decide la validita' del numero.
Ci sono piu' segnali per lo stesso simbolo nello stesso giorno, e condividono lo
stesso forward return: trattarli come indipendenti gonfia la significativita' di
circa un ordine di grandezza. Quindi si riduce a UNA osservazione per
simbolo-giorno, tenendo l'ULTIMO segnale del giorno — che e' esattamente quello
che il ranker usa in produzione — e si calcola lo Spearman cross-sectional giorno
per giorno, mediando poi sui giorni.

Uso:
    uv run python scripts/compute_s4_ic.py
"""
from __future__ import annotations

import json
import math
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import spearmanr

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT = PROJECT_DIR / "docs" / "evidence" / "s4_ic.json"
MIN_SIMBOLI_GIORNO = 5  # sotto, la correlazione cross-sectional e' rumore puro

QUERY = """SELECT date_trunc('day', generated_at)::date, symbol, score, fallback_used,
       forward_return, forward_return_3d, forward_return_5d
FROM sentiment_signals
WHERE forward_return IS NOT NULL
ORDER BY generated_at;"""


def _leggi_segnali() -> dict:
    """Una osservazione per (giorno, simbolo): l'ultimo segnale, come il ranker."""
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", QUERY],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:200]}")

    ultimo: dict[tuple[str, str], dict] = {}
    for riga in res.stdout.strip().split("\n"):
        if not riga.strip():
            continue
        p = riga.split("|")
        if p[4] == "":
            continue
        ultimo[(p[0], p[1])] = {
            "score": float(p[2]),
            "fallback": p[3] == "t",
            1: float(p[4]),
            3: float(p[5]) if p[5] else None,
            5: float(p[6]) if p[6] else None,
        }
    return ultimo


def _serie_ic(per_giorno: dict, filtro, orizzonte: int) -> list[tuple[str, float, int]]:
    """IC cross-sectional per ogni giorno con abbastanza simboli."""
    out = []
    for giorno, righe in sorted(per_giorno.items()):
        sel = [r for r in righe if filtro(r) and r[orizzonte] is not None]
        if len(sel) < MIN_SIMBOLI_GIORNO:
            continue
        scores = [r["score"] for r in sel]
        fwd = [r[orizzonte] for r in sel]
        if len(set(scores)) < 2 or len(set(fwd)) < 2:
            continue  # serie costante: la correlazione non e' definita
        ic = spearmanr(scores, fwd).correlation
        if ic is not None and not math.isnan(ic):
            out.append((giorno, float(ic), len(sel)))
    return out


def _sintesi(serie: list[tuple[str, float, int]]) -> dict:
    """Media, dispersione e t sulla serie giornaliera degli IC.

    Il t si calcola sui GIORNI, non sulle osservazioni: e' il giorno l'unita'
    indipendente, non il singolo segnale.
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


def main() -> int:
    ultimo = _leggi_segnali()
    if not ultimo:
        raise SystemExit("Nessun segnale con forward_return: niente da calcolare.")

    per_giorno: dict[str, list[dict]] = defaultdict(list)
    for (giorno, _sym), v in ultimo.items():
        per_giorno[giorno].append(v)

    sottoinsiemi = {
        "tutti": lambda r: True,
        "ensemble": lambda r: not r["fallback"],
        "fallback": lambda r: r["fallback"],
        "alta_convinzione_0.30": lambda r: abs(r["score"]) >= 0.30,
    }

    risultato: dict = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "metodo": (
            "una osservazione per simbolo-giorno (ultimo segnale, come il ranker); "
            "Spearman cross-sectional giornaliero; t calcolato sui giorni"
        ),
        "osservazioni_simbolo_giorno": len(ultimo),
        "giorni_totali": len(per_giorno),
        "sintesi": {},
        "serie_giornaliera_1g": [],
    }

    for nome, filtro in sottoinsiemi.items():
        risultato["sintesi"][nome] = {
            f"{o}g": _sintesi(_serie_ic(per_giorno, filtro, o)) for o in (1, 3, 5)
        }

    risultato["serie_giornaliera_1g"] = [
        {"giorno": g, "ic": ic, "n_simboli": n}
        for g, ic, n in _serie_ic(per_giorno, lambda r: True, 1)
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(risultato, indent=2, ensure_ascii=False))
    tmp.replace(OUT)  # atomica: mai un file mezzo scritto

    print(f"Scritto: {OUT}")
    print(f"\n{len(ultimo)} osservazioni simbolo-giorno su {len(per_giorno)} giorni\n")
    print(f"{'sottoinsieme':24} {'oriz':5} {'giorni':>6} {'IC medio':>9} {'t':>6} {'sign.':>6}")
    for nome in sottoinsiemi:
        for o in (1, 3, 5):
            s = risultato["sintesi"][nome][f"{o}g"]
            if s["ic_medio"] is None:
                continue
            t = s["t_stat"]
            print(f"{nome:24} {o}g{'':3} {s['giorni']:>6} {s['ic_medio']:>+9.4f} "
                  f"{t:>+6.2f} {'SI' if s['significativo_a_3'] else 'no':>6}")

    tutti_1g = risultato["sintesi"]["tutti"]["1g"]
    if tutti_1g.get("ic_rilevabile_a_t3"):
        print(f"\nCon {tutti_1g['giorni']} giorni rileviamo solo |IC| > "
              f"{tutti_1g['ic_rilevabile_a_t3']:.4f}. L'IC tipico di un segnale")
        print("azionario in letteratura e' 0.02-0.05: se il campione non basta,")
        print("l'esito e' 'non rilevabile', NON 'assente'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
