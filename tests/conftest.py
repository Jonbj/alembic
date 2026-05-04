# tests/conftest.py
import pytest


@pytest.fixture
def sample_news_text():
    return "Apple Inc. reported record quarterly earnings of $1.2B, beating analyst estimates."


@pytest.fixture
def sample_scores():
    return [0.6, 0.5, -0.2, 0.8, -0.1, 0.4, 0.7, -0.3, 0.2, 0.5]


@pytest.fixture
def sample_returns():
    return [0.02, 0.01, -0.015, 0.03, -0.005, 0.01, 0.025, -0.02, 0.005, 0.015]
