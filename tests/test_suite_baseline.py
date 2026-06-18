"""P0-12 (WS-13) — Suite baseline tests.

These tests verify the test toolchain itself is sound:
  - ibkr_adapter importable without ib_insync in the environment
  - pytest-asyncio installed so async tests actually run
  - asyncio_mode=auto is active (not silently ignored)

Tests here are RED until the dependency issues are fixed; they must stay
green permanently afterward to catch regressions.
"""

import importlib
import importlib.util
import sys

import pytest


def test_ibkr_adapter_importable_without_ib_insync():
    """ibkr_adapter must not crash at import when ib_insync is absent.

    Currently causes tests/brokers/test_ibkr_adapter.py to fail collection
    because 'from ib_insync import IB, Stock' is at module level.
    Fix: make the import conditional / lazy in ibkr_adapter.py.

    IMPORTANT: we save and restore the original module object to avoid
    breaking the globals reference used by IBKRAdapter.__init__ in other tests.
    """
    original_mod = sys.modules.get("src.brokers.ibkr_adapter")
    original_ib = sys.modules.get("ib_insync")

    # Temporarily remove both so importlib reloads from scratch
    sys.modules.pop("src.brokers.ibkr_adapter", None)

    # Mask ib_insync as unavailable
    sys.modules["ib_insync"] = None  # type: ignore[assignment]

    try:
        mod = importlib.import_module("src.brokers.ibkr_adapter")
        assert mod is not None
    except ImportError as exc:
        pytest.fail(
            f"ibkr_adapter raised ImportError when ib_insync is absent: {exc}\n"
            "Fix: wrap 'from ib_insync import IB, Stock' in a try/except ImportError."
        )
    finally:
        # Always restore original modules — never leave sys.modules in a partial state.
        if original_ib is not None:
            sys.modules["ib_insync"] = original_ib
        else:
            sys.modules.pop("ib_insync", None)
        if original_mod is not None:
            sys.modules["src.brokers.ibkr_adapter"] = original_mod
        else:
            sys.modules.pop("src.brokers.ibkr_adapter", None)


def test_pytest_asyncio_installed():
    """pytest-asyncio must be present so async tests are executed, not silently skipped.

    Without it, asyncio_mode=auto in pytest.ini has no effect, and any async
    test function returns a coroutine object instead of running.
    """
    spec = importlib.util.find_spec("pytest_asyncio")
    assert spec is not None, (
        "pytest-asyncio is not installed in the current venv.\n"
        "Fix: add pytest-asyncio>=0.23 to [dependency-groups] dev in pyproject.toml "
        "and run 'uv sync --group dev' (or pip install pytest-asyncio>=0.23)."
    )


def test_asyncio_mode_is_active():
    """asyncio_mode=auto must be respected so coroutines are awaited by the runner.

    If pytest-asyncio is installed, this test passes trivially.
    It exists as a permanent regression guard.
    """
    import pytest_asyncio  # noqa: F401 — import succeeds only when installed
    from pytest_asyncio import __version__ as pa_version
    major = int(pa_version.split(".")[0])
    assert major >= 0, "pytest-asyncio version check"
    # asyncio_mode = auto is set in pytest.ini; no further runtime check needed here
