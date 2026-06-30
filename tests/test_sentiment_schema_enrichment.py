"""Point 1 — enriched sentiment schema + prompt (design doc §5/§9).

Verifies the new LLMSentimentOutput fields are backward-compatible (unenriched output
parses with neutral defaults, leaving score = polarity × confidence unchanged) and that
the DK-CoT prompt requests them and forbids a trading action.
"""
from src.models.news import LLMSentimentOutput
from src.workers.sentiment import _DK_COT_PROMPT


class TestSchemaBackwardCompatible:
    def test_parses_without_enriched_fields(self):
        out = LLMSentimentOutput(polarity=0.6, confidence=0.8, reasoning="bull case")
        assert out.event_type == "other"
        assert out.directness == "direct"
        assert out.materiality == 1.0   # neutral → score unchanged
        assert out.novelty == 1.0
        assert out.risk_flags == []
        assert out.evidence_sentences == []

    def test_parses_with_enriched_fields(self):
        out = LLMSentimentOutput(
            polarity=-0.7, confidence=0.82, reasoning="weak guidance",
            event_type="guidance", directness="direct", materiality=0.9, novelty=0.6,
            risk_flags=["already_priced_in"], evidence_sentences=["cut FY guidance"],
        )
        assert out.event_type == "guidance"
        assert out.materiality == 0.9
        assert out.risk_flags == ["already_priced_in"]
        assert out.evidence_sentences == ["cut FY guidance"]

    def test_defaults_are_score_neutral(self):
        # materiality 1.0 × directness("direct")=1.0 → no change to polarity×confidence
        from src.connectors.ticker_resolver import directness_multiplier
        out = LLMSentimentOutput(polarity=0.5, confidence=0.6, reasoning="x")
        assert out.materiality * directness_multiplier(out.directness) == 1.0


class TestPrompt:
    def test_requests_enriched_fields(self):
        for field in ("event_type", "directness", "materiality", "novelty",
                      "risk_flags", "evidence_sentences"):
            assert field in _DK_COT_PROMPT

    def test_forbids_trading_action(self):
        assert "buy/sell/hold" in _DK_COT_PROMPT.lower() or "no buy" in _DK_COT_PROMPT.lower()

    def test_issuer_specific(self):
        assert "issuer-specific" in _DK_COT_PROMPT.lower()
