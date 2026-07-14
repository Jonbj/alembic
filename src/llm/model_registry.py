"""Runtime registry for sentiment LLM models.

The frontend must not hardcode model names: Ollama-backed model availability can
change over time. This module is the backend source of truth for the sentiment
models the current worker path can use.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class SentimentModel:
    key: str
    model_id: str
    label: str
    economy_default: bool = False
    # When False the model is selectable via an explicit token but is NOT part
    # of the "all" expansion — protects live cost/latency from silently growing
    # the ensemble when candidates are registered for pair swaps.
    in_all: bool = True


_MODELS: tuple[SentimentModel, ...] = (
    SentimentModel("kimi", "kimi-k2.6:cloud", "Kimi K2.6"),
    SentimentModel("glm52", "glm-5.2:cloud", "GLM-5.2", economy_default=True),
    # Stage 1 comparison pool (2026-07-10): registered so the live pair can be
    # swapped via config:sentiment_llm_models without a code change.
    SentimentModel("qwen35", "qwen3.5:cloud", "Qwen3.5", in_all=False),
    SentimentModel("gptoss", "gpt-oss:20b-cloud", "GPT-OSS 20B", in_all=False),
)

_ALIASES = {
    "glm": "glm52",
    "glm-5.2": "glm52",
    "glm-5.2:cloud": "glm52",
    "kimi-k2.6": "kimi",
    "kimi-k2.6:cloud": "kimi",
    "qwen": "qwen35",
    "qwen3.5": "qwen35",
    "qwen3.5:cloud": "qwen35",
    "gpt-oss": "gptoss",
    "gpt-oss:20b": "gptoss",
    "gpt-oss:20b-cloud": "gptoss",
}


def sentiment_models() -> list[SentimentModel]:
    """Return models supported by the current sentiment worker implementation."""
    return list(_MODELS)


def valid_selection_tokens() -> set[str]:
    """Return accepted model-selection tokens, including backward-compatible aliases."""
    return {"all", *[m.key for m in _MODELS], *_ALIASES.keys()}


def canonical_model_key(token: str) -> str | None:
    normalized = token.strip().lower()
    if normalized == "all":
        return "all"
    keys = {m.key for m in _MODELS}
    if normalized in keys:
        return normalized
    return _ALIASES.get(normalized)


def economy_model_key() -> str:
    configured = canonical_model_key(environ.get("SENTIMENT_ECONOMY_MODEL", "glm52"))
    if configured and configured != "all":
        return configured
    for model in _MODELS:
        if model.economy_default:
            return model.key
    return _MODELS[-1].key


def normalize_model_selection(raw: str | None) -> tuple[str, list[str], list[str]]:
    """Normalize a comma-separated selection.

    Returns:
        canonical_selection: value safe to persist, e.g. "all" or "kimi,glm52"
        keys: active model keys expanded from "all"
        invalid: rejected input tokens
    """
    if not raw:
        raw = environ.get("SENTIMENT_LLM_MODELS", "all")
    tokens = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if not tokens or "all" in tokens:
        keys = [m.key for m in _MODELS if m.in_all]
        return "all", keys, []

    keys: list[str] = []
    invalid: list[str] = []
    for token in tokens:
        key = canonical_model_key(token)
        if key is None or key == "all":
            invalid.append(token)
            continue
        if key not in keys:
            keys.append(key)

    if not keys:
        keys = [m.key for m in _MODELS if m.in_all]
        return "all", keys, invalid
    # Canonical order: preserve registry order so "gptoss,glm52" canonicalizes
    # to "glm52,gptoss" and two operators never persist visually-different keys.
    registry_order = [m.key for m in _MODELS]
    keys.sort(key=lambda k: registry_order.index(k))
    return ",".join(keys), keys, invalid


def model_ids_for_keys(keys: list[str]) -> list[str]:
    by_key = {m.key: m.model_id for m in _MODELS}
    return [by_key[key] for key in keys if key in by_key]


def default_weights(model_ids: list[str] | None = None) -> dict[str, float]:
    ids = model_ids or [m.model_id for m in _MODELS]
    if not ids:
        return {}
    weight = 1.0 / len(ids)
    return {model_id: weight for model_id in ids}


def normalize_weights_for_active_models(
    weights: dict[str, float] | None,
    active_model_ids: list[str] | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Drop weights for inactive models and renormalize across active models."""
    active_ids = active_model_ids or [m.model_id for m in _MODELS]
    if not active_ids:
        return {}, list((weights or {}).keys())

    raw = weights or {}
    filtered = {
        model_id: float(raw.get(model_id, 0.0))
        for model_id in active_ids
        if float(raw.get(model_id, 0.0)) > 0.0
    }
    dropped = sorted([model_id for model_id in raw.keys() if model_id not in active_ids])
    total = sum(filtered.values())
    if total <= 0:
        return default_weights(active_ids), dropped
    return {model_id: value / total for model_id, value in filtered.items()}, dropped


def sentiment_model_payload(selection: str | None = None) -> dict:
    canonical, keys, invalid = normalize_model_selection(selection)
    active_ids = model_ids_for_keys(keys)
    active_id_set = set(active_ids)
    return {
        "selection": canonical,
        "active_model_ids": active_ids,
        "economy_model": economy_model_key(),
        "invalid": invalid,
        "models": [
            {
                "key": model.key,
                "model_id": model.model_id,
                "label": model.label,
                "active": model.model_id in active_id_set,
                "economy_default": model.key == economy_model_key(),
            }
            for model in _MODELS
        ],
    }


def build_sentiment_clients(keys: list[str]):
    """Instantiate sentiment clients for the selected model keys."""
    from src.llm.client import (
        OllamaGLM52Client,
        OllamaGptOssClient,
        OllamaKimiClient,
        OllamaQwen35Client,
    )

    registry = {
        "kimi": OllamaKimiClient,
        "glm52": OllamaGLM52Client,
        "qwen35": OllamaQwen35Client,
        "gptoss": OllamaGptOssClient,
    }
    clients = [registry[key]() for key in keys if key in registry]
    return clients or [
        registry[model.key]() for model in _MODELS if model.in_all
    ]
