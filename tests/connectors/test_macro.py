"""Tests for macro data connector."""

from unittest.mock import MagicMock, patch

import pytest


class TestFetchVixFromFred:
    """Tests for fetch_vix_from_fred()."""

    def test_returns_float_with_api_key(self):
        """Fetches VIX via authenticated JSON API when api_key provided."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "observations": [{"date": "2026-05-02", "value": "18.45"}]
        }

        with patch("httpx.get", return_value=mock_resp) as mock_get:
            from src.connectors.macro import fetch_vix_from_fred
            result = fetch_vix_from_fred(series_id="VIXCLS", api_key="test-key")

        assert result == pytest.approx(18.45)
        call_kwargs = mock_get.call_args
        assert "api.stlouisfed.org" in call_kwargs[0][0]
        assert call_kwargs[1]["params"]["api_key"] == "test-key"

    def test_returns_float_without_api_key(self):
        """Fetches VIX via public CSV endpoint when no api_key."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "DATE,VIXCLS\n2026-04-30,20.12\n2026-05-01,19.87\n2026-05-02,18.45"

        with patch("httpx.get", return_value=mock_resp) as mock_get:
            from src.connectors.macro import fetch_vix_from_fred
            result = fetch_vix_from_fred(series_id="VIXCLS", api_key="")

        assert result == pytest.approx(18.45)
        assert "fredgraph.csv" in mock_get.call_args[0][0]

    def test_raises_on_http_error(self):
        """Propagates httpx.HTTPStatusError on network failure."""
        import httpx
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_vix_from_fred
            with pytest.raises(httpx.HTTPStatusError):
                fetch_vix_from_fred(series_id="VIXCLS", api_key="test-key")

    def test_raises_on_empty_observations(self):
        """Raises ValueError when FRED returns no observations."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"observations": []}

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_vix_from_fred
            with pytest.raises(ValueError, match="no observations"):
                fetch_vix_from_fred(series_id="VIXCLS", api_key="test-key")

    def test_raises_on_malformed_csv(self):
        """Raises ValueError when CSV response is malformed."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "DATE,VIXCLS\n"  # Only header, no data

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_vix_from_fred
            with pytest.raises(ValueError, match="insufficient lines"):
                fetch_vix_from_fred(series_id="VIXCLS", api_key="")

    def test_raises_on_csv_single_column(self):
        """Raises ValueError when CSV last line has only one column."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "DATE,VIXCLS\n2026-05-02"  # Missing value

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_vix_from_fred
            with pytest.raises(ValueError, match="malformed"):
                fetch_vix_from_fred(series_id="VIXCLS", api_key="")
