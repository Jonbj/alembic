"""Sentiment model registry — the ensemble pair must be swappable via
config:sentiment_llm_models without code changes, so every vetted candidate
(Stage 1 comparison pool) needs a registry entry and a client mapping."""
from src.llm.model_registry import (
    build_sentiment_clients,
    model_ids_for_keys,
    normalize_model_selection,
)


def test_qwen35_is_selectable():
    _, keys, invalid = normalize_model_selection("qwen35,glm52")
    assert invalid == []
    assert set(keys) == {"qwen35", "glm52"}


def test_gptoss_is_selectable():
    _, keys, invalid = normalize_model_selection("gptoss,glm52")
    assert invalid == []
    assert set(keys) == {"gptoss", "glm52"}


def test_model_ids_for_new_keys():
    assert model_ids_for_keys(["qwen35"]) == ["qwen3.5:cloud"]
    assert model_ids_for_keys(["gptoss"]) == ["gpt-oss:20b-cloud"]


def test_build_clients_for_new_keys():
    clients = build_sentiment_clients(["qwen35", "gptoss"])
    assert {c.model_id for c in clients} == {"qwen3.5:cloud", "gpt-oss:20b-cloud"}


def test_all_expansion_excludes_selectable_only_candidates():
    """The live Redis selection is often "all": registering swap candidates must
    NOT silently grow the running ensemble (cost, latency, divergence chaos)."""
    _, keys, invalid = normalize_model_selection("all")
    assert invalid == []
    assert set(keys) == {"kimi", "glm52"}
