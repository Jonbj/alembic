"""Pairwise shadow/live model comparison (Stage 2 auto-report core)."""
import pandas as pd

from src.performance.model_comparison import build_comparison


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
