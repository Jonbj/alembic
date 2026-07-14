"""Shared Stage-2 comparison logic (beat auto-report + manual script — factored
once per the spec; never duplicated)."""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


def build_comparison(
    rows: pd.DataFrame,
    fwd_by_news: dict[int, float],
    divergence_threshold: float = 0.40,
) -> dict:
    """Rank models and model-pairs from (shadow + live) per-model outputs.

    Args:
        rows: columns news_log_id, model_id, polarity, confidence, parse_error.
        fwd_by_news: news_log_id -> forward_return (from sentiment_signals).
        divergence_threshold: live ENSEMBLE_DIVERGENCE_STD for pair replay.

    Returns:
        {"models": {model_id: {n, parse_fail_rate, ic, hit_rate}},
         "pairs":  {"A+B": {n_common, divergence_rate, pair_ic}}}
    """
    out: dict = {"models": {}, "pairs": {}}
    rows = rows.copy()
    rows["fwd"] = rows["news_log_id"].map(fwd_by_news)

    for model_id, g in rows.groupby("model_id"):
        ok = g[~g["parse_error"] & g["fwd"].notna() & g["polarity"].notna()]
        score = ok["polarity"] * ok["confidence"]
        ic = float(score.rank().corr(ok["fwd"].rank())) if len(ok) >= 3 else float("nan")
        hit = float((np.sign(score) == np.sign(ok["fwd"])).mean()) if len(ok) >= 3 else float("nan")
        out["models"][model_id] = {
            "n": int(len(g)),
            "parse_fail_rate": float(g["parse_error"].mean()),
            "ic": ic,
            "hit_rate": hit,
        }

    parsed = rows[~rows["parse_error"] & rows["polarity"].notna()]
    by_news = parsed.pivot_table(index="news_log_id", columns="model_id",
                                 values="polarity", aggfunc="first")
    for a, b in combinations(sorted(out["models"]), 2):
        if a not in by_news.columns or b not in by_news.columns:
            continue
        common = by_news[[a, b]].dropna()
        if common.empty:
            out["pairs"][f"{a}+{b}"] = {"n_common": 0, "divergence_rate": float("nan"),
                                        "pair_ic": float("nan")}
            continue
        stds = common.std(axis=1, ddof=1)  # matches EnsembleAggregator (ddof=1)
        diverged = stds >= divergence_threshold
        agreed = common[~diverged]
        fwd = agreed.index.to_series().map(fwd_by_news)
        pair_score = agreed.mean(axis=1)
        pair_ic = (float(pair_score.rank().corr(fwd.rank()))
                   if fwd.notna().sum() >= 3 else float("nan"))
        out["pairs"][f"{a}+{b}"] = {
            "n_common": int(len(common)),
            "divergence_rate": float(diverged.mean()),
            "pair_ic": pair_ic,
        }
    return out


def _fmt_pct(x: float) -> str:
    return "—" if pd.isna(x) else f"{x:.0%}"


def _fmt_num(x: float) -> str:
    return "—" if pd.isna(x) else f"{x:.3f}"


def render_markdown(report: dict) -> str:
    lines = ["# Stage-2 model comparison", "", "## Models",
             "| model | n | parse_fail | IC | hit rate |", "|---|---|---|---|---|"]
    for m, s in sorted(report["models"].items(),
                       key=lambda kv: -(kv[1]["ic"] if pd.notna(kv[1]["ic"]) else -9)):
        lines.append(f"| {m} | {s['n']} | {_fmt_pct(s['parse_fail_rate'])} "
                     f"| {_fmt_num(s['ic'])} | {_fmt_pct(s['hit_rate'])} |")
    lines += ["", "## Pairs (replayed at live threshold)",
              "| pair | n | divergence | pair IC |", "|---|---|---|---|"]
    for p, s in sorted(report["pairs"].items(),
                       key=lambda kv: kv[1]["divergence_rate"]):
        lines.append(f"| {p} | {s['n_common']} | {_fmt_pct(s['divergence_rate'])} "
                     f"| {_fmt_num(s['pair_ic'])} |")
    return "\n".join(lines)
