"""Configuration module for LLM Trading System."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Config(BaseModel):
    """Application configuration with validation."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    # Paths - configurable from env
    CLAUDE_CLI_PATH: str = Field(
        default_factory=lambda: os.environ.get("CLAUDE_CLI_PATH", "claude")
    )

    # LLM Settings
    LLM_TIMEOUT_SECONDS: int = Field(default=120)
    LLM_MAX_RETRIES: int = Field(default=3)
    LLM_DAILY_BUDGET_USD: float = Field(default=50.0)

    # Model costs (per 1M tokens) - should be loaded from config YAML in production
    MODEL_COSTS: dict[str, tuple[float, float]] = Field(
        default={
            "opus": (15.0, 75.0),  # (input, output)
            "sonnet": (3.0, 15.0),
            "haiku": (0.25, 1.25),
            "qwen3.5:cloud": (2.0, 6.0),
            "deepseek-v4-pro:cloud": (4.0, 12.0),
        }
    )

    # Redis - should come from environment in production
    REDIS_URL: str = Field(
        default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
    REDIS_SIGNAL_TTL_SECONDS: int = Field(default=4 * 3600)

    # PostgreSQL - should come from environment in production
    DATABASE_URL: str = Field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql://localhost:5432/llm_trading"
        )
    )

    # API - REQUIRED secret
    ADMIN_API_KEY: str = Field(default_factory=lambda: os.environ.get("ADMIN_API_KEY", ""))

    # Telegram notifications
    TELEGRAM_BOT_TOKEN: str = Field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    TELEGRAM_CHAT_ID: str = Field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))

    # Ensemble thresholds
    ENSEMBLE_MIN_CONFIDENCE: float = Field(default=0.4)
    ENSEMBLE_DIVERGENCE_STD: float = Field(default=0.30)

    # Fallback settings
    MAX_CONSECUTIVE_FALLBACKS: int = Field(default=3)

    @field_validator("ADMIN_API_KEY")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key is present and has minimum length."""
        if not v or len(v) < 32:
            raise ValueError(
                "ADMIN_API_KEY must be set and at least 32 characters. "
                "Set it via environment variable."
            )
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate DATABASE_URL format."""
        if not v or not v.startswith("postgresql://"):
            raise ValueError(
                "DATABASE_URL must be a valid PostgreSQL URL starting with 'postgresql://'. "
                "Set it via environment variable."
            )
        # Warn for non-localhost connections without SSL
        if "sslmode" not in v and "localhost" not in v:
            import warnings
            warnings.warn(
                "DATABASE_URL without sslmode for non-localhost connection. "
                "Consider adding ?sslmode=require for production.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate REDIS_URL format."""
        if not v or not v.startswith("redis://"):
            raise ValueError(
                "REDIS_URL must be a valid Redis URL starting with 'redis://'. "
                "Set it via environment variable."
            )
        return v

    @field_validator("MODEL_COSTS")
    @classmethod
    def validate_model_costs(cls, v: dict) -> dict:
        """Validate MODEL_COSTS structure and values."""
        for model_id, costs in v.items():
            if not isinstance(costs, tuple) or len(costs) != 2:
                raise ValueError(
                    f"MODEL_COSTS['{model_id}'] must be a tuple of 2 floats (input, output)"
                )
            if costs[0] < 0 or costs[1] < 0:
                raise ValueError(
                    f"MODEL_COSTS['{model_id}'] costs must be non-negative"
                )
        return v

    @field_validator("REDIS_SIGNAL_TTL_SECONDS")
    @classmethod
    def validate_signal_ttl(cls, v: int) -> int:
        """Validate REDIS_SIGNAL_TTL_SECONDS is positive."""
        if v <= 0:
            raise ValueError("REDIS_SIGNAL_TTL_SECONDS must be positive")
        return v

    @field_validator("LLM_DAILY_BUDGET_USD")
    @classmethod
    def validate_budget(cls, v: float) -> float:
        """Validate LLM_DAILY_BUDGET_USD is positive."""
        if v <= 0:
            raise ValueError("LLM_DAILY_BUDGET_USD must be positive")
        return v

    @field_validator("ENSEMBLE_MIN_CONFIDENCE")
    @classmethod
    def validate_ensemble_min_confidence(cls, v: float) -> float:
        """Validate ENSEMBLE_MIN_CONFIDENCE is in [0, 1] range."""
        if v < 0 or v > 1:
            raise ValueError("ENSEMBLE_MIN_CONFIDENCE must be between 0 and 1")
        return v

    @field_validator("ENSEMBLE_DIVERGENCE_STD")
    @classmethod
    def validate_ensemble_divergence_std(cls, v: float) -> float:
        """Validate ENSEMBLE_DIVERGENCE_STD is positive."""
        if v <= 0:
            raise ValueError("ENSEMBLE_DIVERGENCE_STD must be positive")
        return v

    @field_validator("MAX_CONSECUTIVE_FALLBACKS")
    @classmethod
    def validate_max_consecutive_fallbacks(cls, v: int) -> int:
        """Validate MAX_CONSECUTIVE_FALLBACKS is positive."""
        if v <= 0:
            raise ValueError("MAX_CONSECUTIVE_FALLBACKS must be positive")
        return v


# Global config instance
config = Config()


def get_claude_cli_path() -> str:
    """Return the path to the Claude CLI binary."""
    return config.CLAUDE_CLI_PATH


def get_llm_timeout() -> int:
    """Return the LLM timeout in seconds."""
    return config.LLM_TIMEOUT_SECONDS


def get_llm_max_retries() -> int:
    """Return the maximum number of retries for LLM calls."""
    return config.LLM_MAX_RETRIES
