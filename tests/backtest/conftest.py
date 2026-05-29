import numpy as np
import pandas as pd
import pytest
from pathlib import Path


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """Deterministic synthetic OHLCV for testing."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", "2024-12-31", freq="B")
    n = len(dates)

    returns = np.random.normal(0.0003, 0.012, n)
    prices = 100 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
        {
            "Open": prices * (1 + np.random.normal(0, 0.002, n)),
            "High": prices * (1 + np.abs(np.random.normal(0, 0.005, n))),
            "Low": prices * (1 - np.abs(np.random.normal(0, 0.005, n))),
            "Close": prices,
            "Volume": np.random.randint(1_000_000, 50_000_000, n),
            "Adj Close": prices,
        },
        index=dates,
    )

    return df


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"
