"""Configuration module for LLM Trading System."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _load_trading_yaml() -> dict:
    """Load trading configuration from config/trading.yaml."""
    path = Path(__file__).parent.parent / "config" / "trading.yaml"
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def load_trading_config() -> dict[str, Any]:
    """Return the current runtime configuration from ``config/trading.yaml``."""
    return _load_trading_yaml()


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

    # Per-model Ollama timeouts (seconds). Override the class default of 90s.
    # Useful to reduce per-model timeout when a model is known to be rate-limited.
    OLLAMA_KIMI_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("OLLAMA_KIMI_TIMEOUT_SECONDS", "90"))
    )
    OLLAMA_QWEN_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("OLLAMA_QWEN_TIMEOUT_SECONDS", "90"))
    )
    OLLAMA_DEEPSEEK_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("OLLAMA_DEEPSEEK_TIMEOUT_SECONDS", "90"))
    )
    OLLAMA_GLM_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("OLLAMA_GLM_TIMEOUT_SECONDS", "90"))
    )
    OLLAMA_GLM52_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("OLLAMA_GLM52_TIMEOUT_SECONDS", "90"))
    )
    OLLAMA_GPTOSS_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("OLLAMA_GPTOSS_TIMEOUT_SECONDS", "90"))
    )

    # Model costs (per 1M tokens) - should be loaded from config YAML in production
    # All 14 models from models.md (8 general purpose + 6 coding specialized)
    MODEL_COSTS: dict[str, tuple[float, float]] = Field(
        default={
            # General purpose models
            "opus": (15.0, 75.0),  # (input, output) USD per 1M tokens
            "sonnet": (3.0, 15.0),
            "haiku": (0.25, 1.25),
            "qwen3.5:cloud": (2.0, 6.0),
            "deepseek-v4-pro:cloud": (4.0, 12.0),
            "glm-5.1:cloud": (1.5, 4.5),  # Estimated based on GLM pricing tier
            "glm-5.2:cloud": (2.0, 6.0),  # Estimated — flagship GLM, same tier as qwen3.5
            "kimi-k2.6:cloud": (2.5, 7.5),  # Estimated based on Moonshot AI pricing
            "gemma4:31b-cloud": (1.0, 3.0),  # Estimated based on Gemma open pricing
            "gpt-oss:20b-cloud": (1.0, 3.0),  # Estimated — 20B open-weight, same tier as gemma4:31b-cloud
            # Coding specialized models
            "qwen3-coder-next:cloud": (3.0, 9.0),  # Premium coding model
            "devstral-small-2:24b-cloud": (1.5, 4.5),  # 24B params, mid-tier
            "devstral-2:123b-cloud": (6.0, 18.0),  # 123B params, high-tier
            "minimax-m2.1:cloud": (2.0, 6.0),  # Coding specialist
            "qwen3-coder:480b-cloud": (10.0, 30.0),  # 480B params, flagship coding
            "minimax-m2:cloud": (1.5, 4.5),  # Previous gen coding
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

    # API - REQUIRED secret (kept for programmatic / CLI access)
    ADMIN_API_KEY: str = Field(default_factory=lambda: os.environ.get("ADMIN_API_KEY", ""))

    # JWT login system
    ADMIN_USERNAME: str = Field(default_factory=lambda: os.environ.get("ADMIN_USERNAME", "admin"))
    # bcrypt hash of the admin password. Generate with: python -c "from passlib.context import CryptContext; print(CryptContext(['bcrypt']).hash('yourpassword'))"
    ADMIN_PASSWORD_HASH: str = Field(default_factory=lambda: os.environ.get("ADMIN_PASSWORD_HASH", ""))
    # MUST be set in .env for production. Defaults to ephemeral key (tokens invalid across restarts).
    JWT_SECRET_KEY: str = Field(default_factory=lambda: os.environ.get("JWT_SECRET_KEY", ""))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = Field(
        default_factory=lambda: int(os.environ.get("JWT_EXPIRE_MINUTES", "1440"))
    )
    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        ]
    )
    API_LOGIN_RATE_LIMIT: int = Field(
        default_factory=lambda: int(os.environ.get("API_LOGIN_RATE_LIMIT", "5"))
    )
    API_LOGIN_RATE_WINDOW_SECONDS: int = Field(
        default_factory=lambda: int(
            os.environ.get("API_LOGIN_RATE_WINDOW_SECONDS", "300")
        )
    )
    API_ADMIN_ACTION_RATE_LIMIT: int = Field(
        default_factory=lambda: int(os.environ.get("API_ADMIN_ACTION_RATE_LIMIT", "5"))
    )
    API_ADMIN_ACTION_RATE_WINDOW_SECONDS: int = Field(
        default_factory=lambda: int(
            os.environ.get("API_ADMIN_ACTION_RATE_WINDOW_SECONDS", "60")
        )
    )

    # Mobile monitor auth (MOB-02)
    MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default_factory=lambda: int(os.environ.get("MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    )
    MOBILE_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default_factory=lambda: int(os.environ.get("MOBILE_REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    )
    MOBILE_LOGIN_RATE_LIMIT: int = Field(
        default_factory=lambda: int(os.environ.get("MOBILE_LOGIN_RATE_LIMIT", "5"))
    )
    MOBILE_LOGIN_RATE_WINDOW_SECONDS: int = Field(
        default_factory=lambda: int(
            os.environ.get("MOBILE_LOGIN_RATE_WINDOW_SECONDS", "300")
        )
    )
    MOBILE_TOKEN_PEPPER: str = Field(
        default_factory=lambda: os.environ.get("MOBILE_TOKEN_PEPPER", "")
    )
    MIN_SUPPORTED_MOBILE_APP_VERSION: str = Field(
        default_factory=lambda: os.environ.get("MIN_SUPPORTED_MOBILE_APP_VERSION", "1.0.0")
    )
    LATEST_MOBILE_APP_VERSION: str = Field(
        default_factory=lambda: os.environ.get("LATEST_MOBILE_APP_VERSION", "1.0.0")
    )

    # Mobile FCM (MOB-04). Service-account JSON path is mounted at runtime; never commit it.
    FIREBASE_SERVICE_ACCOUNT_PATH: str | None = Field(
        default_factory=lambda: os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH") or None
    )
    FCM_PROJECT_ID: str | None = Field(
        default_factory=lambda: os.environ.get("FCM_PROJECT_ID") or None
    )
    FCM_FAKE_DELIVERY_ENABLED: bool = Field(
        default_factory=lambda: os.environ.get(
            "FCM_FAKE_DELIVERY_ENABLED", "false"
        ).lower()
        in {"1", "true", "yes"}
    )
    FCM_USE_APPLICATION_DEFAULT_CREDENTIALS: bool = Field(
        default_factory=lambda: os.environ.get(
            "FCM_USE_APPLICATION_DEFAULT_CREDENTIALS", "false"
        ).lower()
        in {"1", "true", "yes"}
    )
    # Ollama cloud API
    OLLAMA_API_KEY: str = Field(default_factory=lambda: os.environ.get("OLLAMA_API_KEY", ""))
    OLLAMA_BASE_URL: str = Field(default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "https://ollama.com"))

    # MarketAux news API (primary live news source)
    MARKETAUX_API_KEY: str = Field(default_factory=lambda: os.environ.get("MARKETAUX_API_KEY", ""))

    # Finnhub company-news (clean explicit ticker tagging, US equities, free tier 60/min).
    FINNHUB_API_KEY: str = Field(default_factory=lambda: os.environ.get("FINNHUB_API_KEY", ""))

    # Financial Modeling Prep — historical earnings calendar.
    # Finnhub's calendar/earnings free tier only covers ~30 days of history; FMP's
    # /stable/earnings-calendar covers the full requested range. (FMP Starter cancelled
    # 2026-07-15, #23; key retained for opportunistic historical pulls.)
    FMP_API_KEY: str = Field(default_factory=lambda: os.environ.get("FMP_API_KEY", ""))

    # Ticker resolution (design doc §4). OpenFIGI key is optional (raises rate limits
    # ~25→~250 req/min). SEC requires a User-Agent with a contact for company_tickers.
    OPENFIGI_API_KEY: str = Field(default_factory=lambda: os.environ.get("OPENFIGI_API_KEY", ""))
    SEC_USER_AGENT: str = Field(
        default_factory=lambda: os.environ.get("SEC_USER_AGENT", "Alembic research stefano.delgobbo@gmail.com")
    )

    # Alpaca Markets (execution + news via Benzinga)
    ALPACA_API_KEY: str = Field(default_factory=lambda: os.environ.get("ALPACA_API_KEY", ""))
    ALPACA_SECRET_KEY: str = Field(default_factory=lambda: os.environ.get("ALPACA_SECRET_KEY", ""))
    ALPACA_BASE_URL: str = Field(
        default_factory=lambda: os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    )
    # Single source of truth for paper vs live trading mode.
    # Set ALPACA_PAPER_MODE=false to enable live execution.
    # Defaults to True (paper) — safe default; must be explicitly disabled to go live.
    # Workers must read this field; never derive mode from ALPACA_BASE_URL substring.
    ALPACA_PAPER_MODE: bool = Field(
        default_factory=lambda: os.environ.get("ALPACA_PAPER_MODE", "true").lower() == "true"
    )

    # P0-05: Bracket order with stop-loss is mandatory on all BUY orders.
    # Default is True (safe: stop-loss always on). Set ALPACA_BRACKET_ENABLED=false
    # only when deliberately testing without stop-loss (e.g., fractionable-only paper runs).
    ALPACA_BRACKET_ENABLED: bool = Field(
        default_factory=lambda: os.environ.get("ALPACA_BRACKET_ENABLED", "true").lower() == "true"
    )
    ALPACA_TAKE_PROFIT_PCT: float = Field(
        default_factory=lambda: float(os.environ.get("ALPACA_TAKE_PROFIT_PCT", "0.06"))
    )
    ALPACA_STOP_LOSS_PCT: float = Field(
        default_factory=lambda: float(os.environ.get("ALPACA_STOP_LOSS_PCT", "0.03"))
    )

    # #62/#63 (2026-07-16 PO decision): promote the d_hard disaster-stop from shadow
    # telemetry to a real broker-enforced GTC stop for fractional positions (100% of
    # the book — Alpaca rejects bracket orders on fractional/notional quantities).
    # Default True per the decision; set false only to roll back.
    ALPACA_FRACTIONAL_STOP_ENABLED: bool = Field(
        default_factory=lambda: os.environ.get("ALPACA_FRACTIONAL_STOP_ENABLED", "true").lower() == "true"
    )

    # #199: shadow observes insufficient buying power without changing order size;
    # the operator may opt into cap only after reviewing a full shadow session.
    BUYING_POWER_GATE_MODE: str = Field(
        default_factory=lambda: os.environ.get("BUYING_POWER_GATE_MODE", "shadow")
    )

    # Telegram notifications
    TELEGRAM_BOT_TOKEN: str = Field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    TELEGRAM_CHAT_ID: str = Field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    TELEGRAM_ALLOWED_USER_IDS: list[str] = Field(
        default_factory=lambda: [
            uid.strip()
            for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
            if uid.strip()
        ]
    )

    # Ensemble thresholds
    ENSEMBLE_MIN_CONFIDENCE: float = Field(default=0.4)
    # Raised 0.30 -> 0.40 on 2026-07-09: the qwen3.5->GLM-5.2 pair swap (150d2c2,
    # 2026-06-29) made the 2-model pair disagree far more often, pushing FinBERT-fallback
    # rate from ~15-20% to ~70-86% of signals. FinBERT fallback scores are much weaker
    # (avg |score| 0.07 vs 0.20, confidence 0.33 vs 0.65), so they rarely clear the entry
    # threshold in portfolio_scheduler -> most signals ended in SKIP_THRESHOLD (68% of
    # execution_decisions over 14d) and order flow to Alpaca dropped to a handful/day.
    # Widening the divergence gate lets same-direction-but-different-magnitude
    # disagreement resolve to a weighted-average signal (still confidence-scored, unlike
    # FinBERT) instead of discarding it; opposite-direction disagreement still averages
    # toward ~0 and gets filtered downstream either way, so this doesn't let through
    # genuinely conflicting model output.
    ENSEMBLE_DIVERGENCE_STD: float = Field(default=0.40)

    # Sentiment reversal exit: if a held position's current LLM score drops below
    # this threshold, a forced SELL is submitted in the next portfolio cycle.
    # Default -0.20: clearly negative signal, not just uncertain.
    SENTIMENT_REVERSAL_EXIT_THRESHOLD: float = Field(
        default_factory=lambda: float(
            os.environ.get("SENTIMENT_REVERSAL_EXIT_THRESHOLD", "-0.20")
        )
    )

    # #67: a reversal force-sell must rest on a CURRENT read — much stricter than
    # the BUY path's 4h (2026-07-16: one stale signal reused for 5 SELLs over 97min).
    SENTIMENT_REVERSAL_MAX_AGE_MINUTES: int = Field(
        default_factory=lambda: int(
            os.environ.get("SENTIMENT_REVERSAL_MAX_AGE_MINUTES", "60")
        )
    )

    # #68: after a reversal force-sell, block re-BUYs on the symbol (any strategy)
    # for this many hours — same protection family as the stop-loss cooldown.
    # 0 disables.
    SENTIMENT_REVERSAL_REENTRY_COOLDOWN_HOURS: float = Field(
        default_factory=lambda: float(
            os.environ.get("SENTIMENT_REVERSAL_REENTRY_COOLDOWN_HOURS", "2.0")
        )
    )

    # #107: real account-equity drawdown baseline. The risk-monitor CRITICAL
    # drawdown alert measures peak-to-trough over risk_reports.nav on/after this
    # date, excluding pre-baseline garbage NAV. YYYY-MM-DD.
    RISK_DRAWDOWN_BASELINE_DATE: str = Field(
        default_factory=lambda: os.environ.get("RISK_DRAWDOWN_BASELINE_DATE", "2026-07-04")
    )

    # Signal velocity: rate of change of sentiment score across recent cycles.
    # velocity = scores[0] - scores[-1] over last 3 history entries.
    # If |velocity| > threshold, apply ±boost multiplier to S4 scores.
    SIGNAL_VELOCITY_THRESHOLD: float = Field(
        default_factory=lambda: float(os.environ.get("SIGNAL_VELOCITY_THRESHOLD", "0.30"))
    )
    SIGNAL_VELOCITY_BOOST: float = Field(
        default_factory=lambda: float(os.environ.get("SIGNAL_VELOCITY_BOOST", "0.20"))
    )

    # FIX-03: max age of a news item (from published time) before it is skipped
    # without inference, and before its signal is excluded from the live cycle.
    # Editorial news older than this is priced in; tactical horizon is intraday.
    MAX_NEWS_AGE_HOURS: float = Field(
        default_factory=lambda: float(os.environ.get("MAX_NEWS_AGE_HOURS", "2"))
    )

    # Fallback settings
    MAX_CONSECUTIVE_FALLBACKS: int = Field(default=3)

    # Symbol universe for performance calculations and watchlist filtering.
    # Loaded from config/trading.yaml under the `symbols.watchlist` key.
    # This replaces the previously hardcoded list in performance.py and
    # allows the news-driven pipeline to know which tickers the execution
    # engine monitors without coupling ingestion to a fixed watchlist.
    WATCHLIST_SYMBOLS: list[str] = Field(
        default_factory=lambda: _load_trading_yaml().get("symbols", {}).get("watchlist", [])
    )

    # FRED API
    FRED_API_KEY: str = Field(
        default_factory=lambda: os.environ.get("FRED_API_KEY", "")
    )

    # Auto-apply ensemble weights guardrails
    AUTO_APPLY_ENABLED: bool = Field(
        default_factory=lambda: os.environ.get("AUTO_APPLY_ENABLED", "true").lower() == "true"
    )  # Toggle: set false to disable auto-apply without deploy
    AUTO_APPLY_VIX_THRESHOLD: float = Field(
        default_factory=lambda: float(os.environ.get("AUTO_APPLY_VIX_THRESHOLD", "30.0"))
    )  # Block auto-apply if VIX >= threshold (high volatility = freeze)
    AUTO_APPLY_IC_VARIANCE_THRESHOLD: float = Field(
        default_factory=lambda: float(os.environ.get("AUTO_APPLY_IC_VARIANCE_THRESHOLD", "0.15"))
    )  # Block if std(purified_icir) >= threshold (model disagreement)
    AUTO_APPLY_WEIGHT_DELTA_MAX: float = Field(
        default_factory=lambda: float(os.environ.get("AUTO_APPLY_WEIGHT_DELTA_MAX", "0.15"))
    )  # Block if any weight changes by >= 15 percentage points
    AUTO_APPLY_VIX_REDIS_TTL_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("AUTO_APPLY_VIX_REDIS_TTL_SECONDS", "3600"))
    )  # Cache VIX in Redis for 1 hour to reduce FRED API calls
    AUTO_APPLY_VIX_FRED_SERIES: str = Field(
        default_factory=lambda: os.environ.get("AUTO_APPLY_VIX_FRED_SERIES", "VIXCLS")
    )  # FRED series ID for daily VIX data
    MIN_TRADE_PNL_THRESHOLD: float = Field(
        default_factory=lambda: float(
            _load_trading_yaml().get("risk", {}).get("min_trade_pnl_threshold", 5.0)
        )
    )

    # Regime detection
    REGIME_LLM_MODEL_1: str = Field(
        default_factory=lambda: os.environ.get("REGIME_LLM_MODEL_1", "kimi-k2.6:cloud")
    )
    REGIME_LLM_MODEL_2: str = Field(
        default_factory=lambda: os.environ.get("REGIME_LLM_MODEL_2", "qwen3.5:cloud")
    )
    REGIME_MULTIPLIER_BULL: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_BULL", "1.0"))
    )
    REGIME_MULTIPLIER_SIDEWAYS: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_SIDEWAYS", "0.7"))
    )
    REGIME_MULTIPLIER_BEAR: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_BEAR", "0.4"))
    )
    REGIME_MULTIPLIER_HIGH_VOL: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_HIGH_VOL", "0.2"))
    )
    REGIME_REDIS_TTL_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("REGIME_REDIS_TTL_SECONDS", "259200"))
    )  # 72h — covers the Fri→Mon weekend gap (detector runs Mon-Fri only)

    # S7 (PEAD) settings removed 2026-07-15 — strategy retired (POC-2 FAIL, ALPHA-A3
    # confuted). PEAD_* config fields retired with it; see docs/S7_LIFECYCLE_HISTORY_2026-07-15.md.

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

    @field_validator("CORS_ALLOWED_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        """Require an explicit origin allowlist; wildcard CORS is never valid here."""
        if "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*'")
        return origins

    @field_validator(
        "API_LOGIN_RATE_LIMIT",
        "API_LOGIN_RATE_WINDOW_SECONDS",
        "API_ADMIN_ACTION_RATE_LIMIT",
        "API_ADMIN_ACTION_RATE_WINDOW_SECONDS",
    )
    @classmethod
    def validate_api_rate_limits(cls, value: int) -> int:
        """Reject disabled or nonsensical security limits."""
        if value < 1:
            raise ValueError("API rate-limit values must be positive")
        return value

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

    @field_validator("BUYING_POWER_GATE_MODE")
    @classmethod
    def validate_buying_power_gate_mode(cls, v: str) -> str:
        """Validate the buying-power gate rollout mode."""
        allowed = {"shadow", "cap", "off"}
        if v not in allowed:
            raise ValueError(
                f"BUYING_POWER_GATE_MODE must be one of {sorted(allowed)} (got {v!r})"
            )
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
