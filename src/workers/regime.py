"""RegimeDetector Celery task — daily macro regime classification."""

import asyncio
import logging
from datetime import datetime, timezone

from src.config import config
from src.connectors.macro import fetch_spy_momentum_20d, fetch_vix_from_fred, fetch_yield_curve
from src.llm.client import DeepseekClient, OpusClient, Qwen35Client
from src.models.regime import MacroSnapshot, RegimeLabel, RegimeOutput, RegimeState
from src.notifications.telegram import TelegramNotifier, format_regime_message
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

_REGIME_PROMPT_TEMPLATE = """\
You are a buy-side macro strategist. Analyze the following market data and classify
the current regime into one of: bull, sideways, bear, high_vol.

Market Data:
- VIX: {vix:.1f}  (CBOE Volatility Index)
- Yield Curve (10Y-2Y spread): {yield_curve:.2f}%  (negative = inverted)
- SPY 20d momentum: {spy_momentum:+.1f}%

Quantitative Guidelines (use as anchors, not rigid rules):
- VIX > 30 → high_vol candidate
- T10Y2Y < -0.5% → recession signal (bear)
- SPY 20d < -8% → risk-off (bear)
- SPY 20d in [-3%, +3%] + VIX < 25 → sideways candidate

Reasoning (2 steps max):
1. Classify each signal as bullish/bearish/neutral
2. Synthesize with priority: high_vol > bear > sideways > bull
   Note any signal interactions that justify overriding guidelines.

Output ONLY valid JSON:
{{
  "regime": "bull"|"sideways"|"bear"|"high_vol",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence on macro picture>",
  "data_quality": "complete"|"partial",
  "regime_secondary": "<optional: second-most-likely regime or null>"
}}

Few-shot Examples:

Example 1 (high_vol):
VIX=38, T10Y2Y=-0.8%, SPY=-12%
→ {{"regime": "high_vol", "confidence": 0.92, "reasoning": "Extreme volatility with inverted curve and sharp selloff indicates panic regime", "data_quality": "complete"}}

Example 2 (sideways):
VIX=16, T10Y2Y=+0.4%, SPY=+1.2%
→ {{"regime": "sideways", "confidence": 0.68, "reasoning": "Low volatility and flat momentum suggest range-bound consolidation", "data_quality": "complete", "regime_secondary": "bull"}}

Example 3 (bear):
VIX=24, T10Y2Y=-0.6%, SPY=-7%
→ {{"regime": "bear", "confidence": 0.78, "reasoning": "Inverted yield curve and negative momentum with elevated volatility", "data_quality": "complete"}}"""


def _build_prompt(vix: float, yield_curve: float, spy_momentum: float) -> str:
    return _REGIME_PROMPT_TEMPLATE.format(
        vix=vix, yield_curve=yield_curve, spy_momentum=spy_momentum
    )


def _make_llm_client(model_id: str) -> OpusClient | Qwen35Client | DeepseekClient:
    """Instantiate an LLM client by model_id string."""
    registry: dict[str, type[OpusClient | Qwen35Client | DeepseekClient]] = {
        "opus": OpusClient,
        "qwen3.5:cloud": Qwen35Client,
        "deepseek-v4-pro:cloud": DeepseekClient,
    }
    cls = registry.get(model_id)
    if cls is None:
        raise ValueError(
            f"Unknown model_id {model_id!r}. Available: {sorted(registry)}"
        )
    return cls()


async def _run_llm_pair(
    prompt: str,
    client1: OpusClient | Qwen35Client | DeepseekClient,
    client2: OpusClient | Qwen35Client | DeepseekClient,
) -> tuple[RegimeOutput | None, RegimeOutput | None]:
    """Run two LLM clients in parallel. Returns None for any that fail."""
    results = await asyncio.gather(
        client1.complete(prompt, RegimeOutput),
        client2.complete(prompt, RegimeOutput),
        return_exceptions=True,
    )
    r1 = results[0] if not isinstance(results[0], BaseException) else None
    r2 = results[1] if not isinstance(results[1], BaseException) else None
    if isinstance(results[0], BaseException):
        log.warning("LLM-1 failed in regime detection: %s", results[0])
    if isinstance(results[1], BaseException):
        log.warning("LLM-2 failed in regime detection: %s", results[1])
    return r1, r2


@app.task(name="src.workers.regime.detect_regime")
def detect_regime() -> None:
    """Classify daily macro regime and update qc:sizing_multiplier in Redis.

    Guardrail cascade:
      - Macro fetch fails → no Redis write, Telegram 🚨
      - Both LLMs fail → no Redis write, Telegram 🚨
      - data_quality partial → no Redis write, Telegram ⚠️
      - Disagreement → conservative (lower) multiplier, Telegram ⚠️ on change
      - Consensus → apply regime, Telegram 📊 only if regime changed
    """
    redis = RedisStore()
    notifier = TelegramNotifier()

    # 1. Fetch macro data
    try:
        vix = fetch_vix_from_fred(
            series_id=config.AUTO_APPLY_VIX_FRED_SERIES,
            api_key=config.FRED_API_KEY,
        )
        yield_curve = fetch_yield_curve(api_key=config.FRED_API_KEY)
        spy_momentum = fetch_spy_momentum_20d()
    except Exception as e:
        log.error("Failed to fetch macro data for regime detection: %s", e)
        try:
            asyncio.run(notifier.send_alert(
                "🚨 RegimeDetector fallito — dati macro non disponibili. Regime invariato.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for macro fetch failure")
        return

    # 1b. Validate macro data ranges
    if not (5.0 <= vix <= 100.0):
        log.error("VIX out of reasonable range: %.1f", vix)
        try:
            asyncio.run(notifier.send_alert(
                f"🚨 RegimeDetector: VIX fuori range ({vix:.1f}). Regime invariato.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for VIX validation")
        return
    if not (-5.0 <= yield_curve <= 5.0):
        log.error("Yield curve out of reasonable range: %.2f%%", yield_curve)
        try:
            asyncio.run(notifier.send_alert(
                f"🚨 RegimeDetector: yield curve fuori range ({yield_curve:.2f}%). Regime invariato.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for yield curve validation")
        return
    if not (-50.0 <= spy_momentum <= 50.0):
        log.error("SPY momentum out of reasonable range: %.1f%%", spy_momentum)
        try:
            asyncio.run(notifier.send_alert(
                f"🚨 RegimeDetector: SPY momentum fuori range ({spy_momentum:+.1f}%). Regime invariato.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for SPY momentum validation")
        return

    # 2. Run 2 LLMs in parallel
    prompt = _build_prompt(vix, yield_curve, spy_momentum)
    client1 = _make_llm_client(config.REGIME_LLM_MODEL_1)
    client2 = _make_llm_client(config.REGIME_LLM_MODEL_2)
    r1, r2 = asyncio.run(_run_llm_pair(prompt, client1, client2))

    # CASO 1: both fail
    if r1 is None and r2 is None:
        log.error("Both LLMs failed in detect_regime")
        try:
            asyncio.run(notifier.send_alert(
                "🚨 RegimeDetector fallito — regime invariato. Controllare i log.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for both LLMs failure")
        return

    # CASO 2: one fails — use the other for both
    if r1 is None:
        # LLM-1 failed, check if LLM-2 has partial data
        if r2.data_quality == "partial":
            log.warning("LLM-1 failed, LLM-2 has partial data quality — skipping Redis write")
            try:
                asyncio.run(notifier.send_alert(
                    "⚠️ RegimeDetector: dati macro incompleti — regime invariato.",
                    level="warning",
                ))
            except Exception:
                log.exception("Failed to send Telegram alert for partial data quality")
            return
        r1 = r2
    elif r2 is None:
        # LLM-2 failed, check if LLM-1 has partial data
        if r1.data_quality == "partial":
            log.warning("LLM-2 failed, LLM-1 has partial data quality — skipping Redis write")
            try:
                asyncio.run(notifier.send_alert(
                    "⚠️ RegimeDetector: dati macro incompleti — regime invariato.",
                    level="warning",
                ))
            except Exception:
                log.exception("Failed to send Telegram alert for partial data quality")
            return
        r2 = r1

    # CASO 3: partial data quality
    if r1.data_quality == "partial" or r2.data_quality == "partial":
        log.warning("Partial data quality in regime detection — skipping Redis write")
        try:
            asyncio.run(notifier.send_alert(
                "⚠️ RegimeDetector: dati macro incompleti — regime invariato.",
                level="warning",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for partial data quality")
        return

    # CASO 4/5: build multiplier map and apply consensus
    multipliers: dict[RegimeLabel, float] = {
        "bull": config.REGIME_MULTIPLIER_BULL,
        "sideways": config.REGIME_MULTIPLIER_SIDEWAYS,
        "bear": config.REGIME_MULTIPLIER_BEAR,
        "high_vol": config.REGIME_MULTIPLIER_HIGH_VOL,
    }

    # Validate regime labels from LLM outputs
    valid_regimes = set(multipliers.keys())
    if r1.regime not in valid_regimes:
        log.error("LLM-1 returned invalid regime: %s", r1.regime)
        try:
            asyncio.run(notifier.send_alert(
                f"🚨 RegimeDetector: LLM-1 ha ritornato regime invalido ({r1.regime}). Regime invariato.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for invalid regime")
        return
    if r2.regime not in valid_regimes:
        log.error("LLM-2 returned invalid regime: %s", r2.regime)
        try:
            asyncio.run(notifier.send_alert(
                f"🚨 RegimeDetector: LLM-2 ha ritornato regime invalido ({r2.regime}). Regime invariato.",
                level="error",
            ))
        except Exception:
            log.exception("Failed to send Telegram alert for invalid regime")
        return

    disagreement = r1.regime != r2.regime
    if disagreement:
        # Select the most conservative regime (lowest multiplier)
        # Explicit comparison to avoid min() key function issues
        regime: RegimeLabel = (
            r1.regime if multipliers[r1.regime] <= multipliers[r2.regime] else r2.regime
        )
        log.info(
            "LLM disagreement resolved: %s(×%.1f) vs %s(×%.1f) → selected %s",
            r1.regime, multipliers[r1.regime],
            r2.regime, multipliers[r2.regime],
            regime,
        )
    else:
        regime = r1.regime

    multiplier = multipliers[regime]

    # 3. Persist state
    previous = redis.get_regime()
    snapshot = MacroSnapshot(vix=vix, yield_curve=yield_curve, spy_momentum_20d=spy_momentum)
    state = RegimeState(
        regime=regime,
        multiplier=multiplier,
        macro_snapshot=snapshot,
        llm_outputs=[r1.model_dump(), r2.model_dump()],
        disagreement=disagreement,
        detected_at=datetime.now(timezone.utc),
    )

    redis.set_regime(state, ttl=config.REGIME_REDIS_TTL_SECONDS)
    redis.set_qc_sizing_multiplier(multiplier, ttl=config.REGIME_REDIS_TTL_SECONDS)

    # 4. Telegram — only if regime changed or first run
    regime_changed = previous is None or previous.regime != regime
    if regime_changed:
        prev_label = previous.regime if previous else None
        msg = format_regime_message(state, prev_label, disagreement)
        level = "info" if regime in ("bull", "sideways") else "warning"
        asyncio.run(notifier.send_alert(msg, level=level))

    log.info("Regime detected: %s (×%.1f), disagreement=%s", regime, multiplier, disagreement)
