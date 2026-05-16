"""Tests for NewsAPIConnector."""
import pytest
from src.connectors.newsapi import NewsAPIConnector, NewsAPIAuthError, NewsAPIRateLimitError


def test_connector_instantiates():
    conn = NewsAPIConnector(api_key="test-key")
    assert conn is not None


def test_raises_auth_error_class_exists():
    with pytest.raises(NewsAPIAuthError):
        raise NewsAPIAuthError("bad key")


def test_raises_rate_limit_error_class_exists():
    with pytest.raises(NewsAPIRateLimitError):
        raise NewsAPIRateLimitError("limit reached")
