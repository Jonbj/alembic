"""Helper puri dei POC S7 revival (small/mid PEAD + transcript tone)."""
from __future__ import annotations

import pytest

from scripts.s7_poc_helpers import (
    classify_cap,
    adv_usd,
    gate_verdict_smallmid,
    reported_quarter_candidates,
    parse_tone_json,
    spearman_ic,
)


class _Bar:
    def __init__(self, day: str, close: float, volume: float):
        from datetime import datetime, timezone
        self.timestamp = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        self.close = close
        self.volume = volume


class TestClassifyCap:
    def test_buckets(self):
        assert classify_cap(150.0) == "micro"        # < $300M: escluso
        assert classify_cap(2_000.0) == "small/mid"  # $300M–$10B
        assert classify_cap(50_000.0) == "large"
        assert classify_cap(0.0) == "unknown"


class TestAdvUsd:
    def test_mean_dollar_volume_before_event_only(self):
        bars = [_Bar(f"2026-03-{d:02d}", 10.0, 1_000_000) for d in range(2, 12)]
        # 10 barre da $10M ADV ciascuna, tutte prima dell'evento
        assert adv_usd(bars, "2026-03-15", lookback=5) == pytest.approx(10_000_000)

    def test_excludes_bars_on_or_after_event(self):
        bars = [_Bar("2026-03-10", 10.0, 1_000_000), _Bar("2026-03-16", 999.0, 9e9)]
        assert adv_usd(bars, "2026-03-15", lookback=5) == pytest.approx(10_000_000)

    def test_empty_returns_zero(self):
        assert adv_usd([], "2026-03-15") == 0.0


class TestGateVerdict:
    def test_pass_case(self):
        rets = [0.03] * 40  # 3% excess lordo, netto 30bps = 2.7%
        v = gate_verdict_smallmid(rets, cost_bps=30)
        assert v["n"] == 40 and v["mean_net"] == pytest.approx(0.027)
        assert v["hit_net"] == 1.0 and v["verdict"] == "PASS"

    def test_fail_on_low_n(self):
        assert gate_verdict_smallmid([0.03] * 29, cost_bps=30)["verdict"] == "FAIL"

    def test_haircut_can_flip_verdict(self):
        rets = [0.016] * 40  # lordo sopra soglia, netto 1.3% < 1.5%
        assert gate_verdict_smallmid(rets, cost_bps=30)["verdict"] == "FAIL"


class TestReportedQuarterCandidates:
    def test_mid_year_event_reports_previous_quarter(self):
        # call di fine aprile → riporta il Q1 fiscale; fallback Q4 anno prima
        assert reported_quarter_candidates("2026-04-24") == ["2026Q1", "2025Q4"]

    def test_january_event_rolls_over_year(self):
        assert reported_quarter_candidates("2026-01-15") == ["2025Q4", "2025Q3"]

    def test_garbage_returns_empty(self):
        assert reported_quarter_candidates("") == []
        assert reported_quarter_candidates("not-a-date") == []


class TestParseToneJson:
    def test_extracts_json_block_from_chatter(self):
        raw = 'Reasoning...\n{"tone_polarity": 0.6, "confidence": 0.8, "guidance": "raised", "key_evidence": "x"}\nDone.'
        d = parse_tone_json(raw)
        assert d["tone_polarity"] == 0.6 and d["guidance"] == "raised"

    def test_clamps_out_of_range(self):
        raw = '{"tone_polarity": 1.7, "confidence": 1.2, "guidance": "none", "key_evidence": ""}'
        d = parse_tone_json(raw)
        assert d["tone_polarity"] == 1.0 and d["confidence"] == 1.0

    def test_invalid_returns_none(self):
        assert parse_tone_json("no json here") is None
        assert parse_tone_json('{"tone_polarity": "alto"}') is None


class TestSpearmanIC:
    def test_perfect_monotonic(self):
        assert spearman_ic([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_perfect_inverse(self):
        assert spearman_ic([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_needs_min_two(self):
        assert spearman_ic([1], [2]) is None
