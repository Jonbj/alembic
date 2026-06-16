"""S7 PEAD Celery worker tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.pead_worker import run_pead_ingestion_worker


_NOW = datetime(2024, 6, 10, 15, 0, 0, tzinfo=timezone.utc)


class TestPeadWorkerNoFilings:
    def test_runs_without_error_when_no_filings(self) -> None:
        """Worker completes cleanly when EDGAR returns no 8-K filings."""
        mock_redis = MagicMock()
        mock_redis.is_processed.return_value = True  # all "already processed"

        with (
            patch("src.workers.pead_worker.SECEdgarConnector") as mock_connector_cls,
            patch("src.workers.pead_worker.RedisStore", return_value=mock_redis),
            patch("src.workers.pead_worker.run_async", return_value=None),
        ):
            mock_connector_cls.return_value = MagicMock()
            # Should not raise
            run_pead_ingestion_worker()


class TestPeadWorkerDeduplication:
    def test_already_processed_filing_skipped(self) -> None:
        """Worker does not re-classify an 8-K it has already seen."""
        from src.models.news import NewsItem

        existing_item = NewsItem(
            id="filing-123",
            source="sec_edgar",
            timestamp=_NOW,
            title="AAPL — 8-K",
            body="Q2 results",
            url="https://sec.gov",
            language="en",
            asset_tags=["AAPL"],
        )

        mock_redis = MagicMock()
        mock_redis.is_pead_processed.return_value = True  # already seen

        with (
            patch("src.workers.pead_worker.SECEdgarConnector") as mock_cls,
            patch("src.workers.pead_worker.RedisStore", return_value=mock_redis),
            patch("src.workers.pead_worker.EarningsSurpriseClassifier") as mock_classifier_cls,
            patch("src.workers.pead_worker.run_async") as mock_run_async,
        ):
            mock_cls.return_value = MagicMock()
            mock_run_async.return_value = [existing_item]

            run_pead_ingestion_worker()

            # Classifier should not have been called
            mock_classifier_cls.return_value.to_signal.assert_not_called()


class TestPeadWorkerBeatSignalStored:
    def test_beat_filing_stored_in_redis(self) -> None:
        """A beat filing produces a SurpriseSignal written to Redis."""
        from src.models.news import NewsItem
        from src.models.pead import EarningsLLMOutput, SurpriseSignal
        from datetime import timedelta

        filing = NewsItem(
            id="filing-456",
            source="sec_edgar",
            timestamp=_NOW,
            title="MSFT — 8-K",
            body="Beat Q3 EPS of $2.94 vs consensus $2.78",
            url="https://sec.gov/msft",
            language="en",
            asset_tags=["MSFT"],
        )
        llm_output = EarningsLLMOutput(
            ticker="MSFT",
            filing_type="earnings_8k",
            eps_actual=2.94,
            eps_consensus=2.78,
            surprise_pct=0.058,
            direction="beat",
            guidance="revised-up",
            confidence=0.88,
            reasoning="Strong beat across all segments",
        )
        expected_signal = SurpriseSignal(
            symbol="MSFT",
            direction="beat",
            surprise_pct=0.058,
            confidence=0.88,
            filing_id="filing-456",
            detected_at=_NOW,
            hold_until=_NOW + timedelta(days=20),
        )

        mock_redis = MagicMock()
        mock_redis.is_pead_processed.return_value = False

        with (
            patch("src.workers.pead_worker.SECEdgarConnector") as mock_cls,
            patch("src.workers.pead_worker.RedisStore", return_value=mock_redis),
            patch("src.workers.pead_worker.EarningsSurpriseClassifier") as mock_classifier_cls,
            patch("src.workers.pead_worker.run_async") as mock_run_async,
        ):
            mock_cls.return_value = MagicMock()
            # First call: _fetch_8k_items → [filing]; second: _classify_filing → llm_output
            mock_run_async.side_effect = [[filing], llm_output]

            mock_classifier = MagicMock()
            mock_classifier.to_signal.return_value = expected_signal
            mock_classifier_cls.return_value = mock_classifier

            run_pead_ingestion_worker()

            mock_redis.write_pead_signal.assert_called_once()
            written = mock_redis.write_pead_signal.call_args[0][0]
            assert written.symbol == "MSFT"
            assert written.direction == "beat"


class TestPeadWorkerLLMFailure:
    def test_llm_failure_does_not_crash_worker(self) -> None:
        """If LLM raises, worker logs and continues to next filing."""
        from src.models.news import NewsItem

        filing = NewsItem(
            id="filing-err",
            source="sec_edgar",
            timestamp=_NOW,
            title="AMZN — 8-K",
            body="Q3 results",
            url="https://sec.gov/amzn",
            language="en",
            asset_tags=["AMZN"],
        )

        mock_redis = MagicMock()
        mock_redis.is_pead_processed.return_value = False

        with (
            patch("src.workers.pead_worker.SECEdgarConnector") as mock_cls,
            patch("src.workers.pead_worker.RedisStore", return_value=mock_redis),
            patch("src.workers.pead_worker.EarningsSurpriseClassifier") as mock_classifier_cls,
            patch("src.workers.pead_worker.run_async") as mock_run_async,
        ):
            mock_cls.return_value = MagicMock()
            # First call (_fetch_8k_items) returns [filing]; second (_classify_filing) raises
            mock_run_async.side_effect = [[filing], Exception("LLM timeout")]

            mock_classifier_cls.return_value = MagicMock()

            # Should not raise — worker absorbs errors per filing
            run_pead_ingestion_worker()

            mock_redis.write_pead_signal.assert_not_called()
