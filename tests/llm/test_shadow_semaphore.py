"""Tests for shadow-mode semaphore (Stage 2 model comparison concurrency).

The shadow semaphore is a separate pool (3 slots) for stage-2 shadow candidate
models, ensuring their load never competes with the live ensemble calls.
"""
from src.llm.client import _ollama_shadow_sem, _ollama_sem


def test_shadow_semaphore_is_separate_pool():
    """Shadow semaphore must have its own key and slot allocation."""
    assert _ollama_shadow_sem._key == "ollama:sem:shadow"
    assert _ollama_shadow_sem._key != _ollama_sem._key
    assert _ollama_shadow_sem._slots == 3
