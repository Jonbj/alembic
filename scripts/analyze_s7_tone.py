#!/usr/bin/env python3
"""POC-2c: IC del tone score vs excess return 20d + gate ALPHA-A3 pre-registrato.

Join: tone_scores.csv (kimi) × eventi (alpha_a5 large + poc1 small/mid) sui campi
(symbol, event_date). Excess: vs SPY per i large (già nel CSV alpha_a5), vs IWM
per gli small/mid (CSV poc1). Gate: n>=30, Spearman IC >= +0.10, spread terzili
top-bottom >= +1.5%, IC > 0 in entrambe le metà (split per data evento).
In più: agreement kimi/glm sul subsample e concordanza guidance vs surprise (A4-lite).
"""
from __future__ import annotations

import csv
import glob
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.s7_poc_helpers import spearman_ic  # noqa: E402


def _load_returns() -> dict[tuple, dict]:
    out = {}
    with open("reports/s7_backtest/alpha_a5_events_2026-07-03.csv") as f:
        for r in csv.DictReader(f):
            if r.get("excess_20d") not in ("", None):
                out[(r["symbol"], r["date"])] = {"excess": float(r["excess_20d"]),
                                                 "surprise": float(r["surprise"])}
    for p in sorted(glob.glob("reports/s7_poc/poc1_smallmid_events_*.csv")):
        with open(p) as f:
            for r in csv.DictReader(f):
                out[(r["symbol"], r["date"])] = {"excess": float(r["excess_20d"]),
                                                 "surprise": float(r["surprise"])}
    return out


def main() -> None:
    rets = _load_returns()
    kimi, glm = {}, {}
    with open("reports/s7_poc/tone_scores.csv") as f:
        for r in csv.DictReader(f):
            k = (r["symbol"], r["event_date"])
            d = {"score": float(r["score"]), "guidance": r["guidance"]}
            (kimi if r["model"].startswith("kimi") else glm)[k] = d

    joined = [(k, kimi[k]["score"], rets[k]["excess"], rets[k]["surprise"], kimi[k]["guidance"])
              for k in sorted(kimi) if k in rets]
    n = len(joined)
    print(f"Eventi con tone (kimi) e ritorno: n={n}")
    if n == 0:
        print("Nessun match — INCONCLUSIVE_DATA"); return

    scores = [j[1] for j in joined]
    excess = [j[2] for j in joined]
    ic = spearman_ic(scores, excess)
    print(f"Spearman IC(tone, excess_20d): {ic:+.3f}")

    order = sorted(joined, key=lambda j: j[1])
    third = max(n // 3, 1)
    bot = [j[2] for j in order[:third]]
    top = [j[2] for j in order[-third:]]
    spread = st.mean(top) - st.mean(bot)
    print(f"Terzili: top {st.mean(top):+.2%} vs bottom {st.mean(bot):+.2%} → spread {spread:+.2%}")

    half = n // 2  # split temporale: ordina per data evento
    by_date = sorted(joined, key=lambda j: j[0][1])
    ic1 = spearman_ic([j[1] for j in by_date[:half]], [j[2] for j in by_date[:half]])
    ic2 = spearman_ic([j[1] for j in by_date[half:]], [j[2] for j in by_date[half:]])
    print(f"Split-half per data: IC prima metà {ic1:+.3f}, seconda metà {ic2:+.3f}")

    # IC del tone DENTRO i soli BEAT: il tone aggiunge oltre il segno della surprise?
    beats = [j for j in joined if j[3] > 0]
    ic_beat = spearman_ic([j[1] for j in beats], [j[2] for j in beats]) if len(beats) > 2 else None
    print(f"IC dentro i soli BEAT (n={len(beats)}): {ic_beat if ic_beat is None else f'{ic_beat:+.3f}'}")

    # A4-lite: concordanza guidance vs segno surprise
    conc = [(j[4] == "raised") == (j[3] > 0) for j in joined if j[4] in ("raised", "lowered")]
    if conc:
        print(f"Concordanza guidance/surprise: {sum(conc) / len(conc):.0%} (n={len(conc)})")

    # Agreement kimi/glm sul subsample
    both = [(kimi[k]["score"], glm[k]["score"]) for k in kimi if k in glm]
    if len(both) > 2:
        agree_ic = spearman_ic([b[0] for b in both], [b[1] for b in both])
        print(f"Agreement kimi/glm (subsample n={len(both)}): Spearman {agree_ic:+.3f}")

    ok = (n >= 30 and ic is not None and ic >= 0.10 and spread >= 0.015
          and ic1 is not None and ic2 is not None and ic1 > 0 and ic2 > 0)
    tag = "INCONCLUSIVE_DATA" if n < 30 else ("PASS" if ok else "FAIL")
    print(f"\n## GATE ALPHA-A3: {tag}")


if __name__ == "__main__":
    main()
