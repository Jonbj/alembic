"""Pairwise shadow/live model comparison (Stage 2 auto-report core)."""
import math

import pandas as pd

from src.performance.model_comparison import build_comparison, render_markdown


def _rows():
    # 4 news items; model A ~tracks fwd, model B anti-tracks, both agree on 2 items.
    return pd.DataFrame([
        # news_log_id, model_id, polarity, confidence, parse_error
        (1, "A", 0.8, 0.9, False), (1, "B", 0.7, 0.8, False),
        (2, "A", -0.6, 0.8, False), (2, "B", -0.5, 0.9, False),
        (3, "A", 0.9, 0.9, False), (3, "B", -0.9, 0.8, False),   # divergent pair
        (4, "A", 0.5, 0.7, False), (4, "B", None, None, True),   # B parse fail
    ], columns=["news_log_id", "model_id", "polarity", "confidence", "parse_error"])


def _fwd():
    return {1: 0.02, 2: -0.01, 3: 0.03, 4: 0.01}


def test_per_model_stats():
    report = build_comparison(_rows(), _fwd(), divergence_threshold=0.40)
    a = report["models"]["A"]
    assert a["n"] == 4 and a["parse_fail_rate"] == 0.0
    b = report["models"]["B"]
    assert b["parse_fail_rate"] == 0.25
    assert a["ic"] > 0        # A tracks forward returns directionally


def test_pairwise_divergence_rate():
    report = build_comparison(_rows(), _fwd(), divergence_threshold=0.40)
    pair = report["pairs"]["A+B"]
    # 3 items where both parsed; item 3 diverges (std of 0.9/-0.9 >= 0.40)
    assert pair["n_common"] == 3
    assert abs(pair["divergence_rate"] - 1 / 3) < 1e-9


def test_hit_rate_nan_below_min_samples():
    # Model C has only 2 valid (non-parse-error) samples: below the n>=3 floor
    # used for ic, so hit_rate must also be NaN rather than a misleading 0%/100%.
    rows = pd.DataFrame([
        (1, "C", 0.8, 0.9, False),
        (2, "C", -0.6, 0.8, False),
        (3, "C", None, None, True),
    ], columns=["news_log_id", "model_id", "polarity", "confidence", "parse_error"])
    fwd = {1: 0.02, 2: -0.01, 3: 0.01}
    report = build_comparison(rows, fwd, divergence_threshold=0.40)
    c = report["models"]["C"]
    assert math.isnan(c["ic"])
    assert math.isnan(c["hit_rate"])


def test_render_markdown_sorts_nan_ic_model_last():
    # Regression test: a naive `-(ic or -9)` sort key leaves NaN as NaN (since
    # NaN is truthy), giving unstable ordering. A model with a real IC must
    # sort above a model with a NaN IC (e.g. too few samples).
    report = {
        "models": {
            "SPARSE": {"n": 1, "parse_fail_rate": 0.0, "ic": float("nan"),
                       "hit_rate": float("nan")},
            "REAL": {"n": 10, "parse_fail_rate": 0.0, "ic": 0.5,
                     "hit_rate": 0.7},
        },
        "pairs": {},
    }
    md = render_markdown(report)
    assert md.index("| REAL ") < md.index("| SPARSE ")
    assert "nan" not in md.lower()
