"""Telegram notifications for trading system alerts."""

import json
from datetime import date, datetime, timezone

import httpx

from src.config import config


class TelegramNotifier:
    """
    Send alerts to Telegram channel.

    Used for:
    - Kill-switch activation
    - Budget exhaustion
    - Consecutive fallback alerts (3+ → QC sizing ×0.5)
    - Drift detection (RED/YELLOW)
    - Performance reports

    Usage:
        notifier = TelegramNotifier()
        await notifier.send_alert("Kill-switch activated: VIX spike detected")
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ):
        """Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Channel or group ID to send messages to
        """
        self._bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self._chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self._enabled = bool(self._bot_token and self._chat_id)

    async def send_alert(
        self,
        message: str,
        level: str = "info",
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Send alert message to Telegram.

        Args:
            message: Message text (supports HTML markup)
            level: Alert level ("info", "warning", "error", "critical")
            parse_mode: Parse mode ("HTML" or "Markdown")

        Returns:
            True if sent successfully, False if disabled or failed
        """
        if not self._enabled:
            print(f"TelegramNotifier: Disabled (no bot_token/chat_id)")
            return False

        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(
            level, "ℹ️"
        )

        full_message = f"{emoji} <b>[LLM Trading]</b>\n\n{message}"

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": full_message,
                        "parse_mode": parse_mode,
                    },
                )
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"TelegramNotifier: Failed to send alert: {e}")
            return False

    async def send_fallback_alert(self, count: int) -> bool:
        """
        Send alert when fallback counter reaches threshold.

        Args:
            count: Number of consecutive fallbacks
        """
        message = (
            f"<b>Ensemble Fallback Alert</b>\n\n"
            f"Consecutive fallbacks: <b>{count}</b>\n"
            f"Threshold: {config.MAX_CONSECUTIVE_FALLBACKS}\n\n"
            f"<b>Action taken:</b>\n"
            f"• QuantConnect position sizing reduced to 50%\n"
            f"• System will auto-recover after 24h without fallbacks\n\n"
            f"<i>Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
        )
        return await self.send_alert(message, level="warning")

    async def send_killswitch_alert(self, reason: str) -> bool:
        """
        Send alert when kill-switch is activated.

        Args:
            reason: Reason for kill-switch activation
        """
        message = (
            f"<b>🚨 KILL-SWITCH ACTIVATED</b>\n\n"
            f"<b>Reason:</b> {reason}\n"
            f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"<b>Actions:</b>\n"
            f"• All trading halted\n"
            f"• Open positions will be managed by safe-mode logic\n"
            f"• Manual intervention required to resume"
        )
        return await self.send_alert(message, level="critical")

    async def send_budget_alert(self, spent: float, limit: float) -> bool:
        """
        Send alert when LLM budget is exhausted.

        Args:
            spent: Amount spent today
            limit: Daily budget limit
        """
        message = (
            f"<b>LLM Budget Exhausted</b>\n\n"
            f"Spent today: <b>${spent:.2f}</b>\n"
            f"Daily limit: <b>${limit:.2f}</b>\n\n"
            f"<b>Action:</b>\n"
            f"• LLM calls blocked until midnight UTC\n"
            f"• System falling back to FinBERT only\n\n"
            f"<i>Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
        )
        return await self.send_alert(message, level="warning")

    async def send_drift_alert(self, drift_level: str, psi_90d: float) -> bool:
        """
        Send alert when drift is detected.

        Args:
            drift_level: "YELLOW" or "RED"
            psi_90d: PSI value for 90-day comparison
        """
        emoji = "⚠️" if drift_level == "YELLOW" else "🚨"
        message = (
            f"{emoji} <b>Drift Detected</b>\n\n"
            f"Level: <b>{drift_level}</b>\n"
            f"PSI (90-day): <b>{psi_90d:.4f}</b>\n\n"
            f"<b>Actions:</b>\n"
            + (
                "• Weight updates frozen\n"
                "• Monitoring increased to hourly\n"
                if drift_level == "YELLOW"
                else "• Trading halted\n"
                "• Model retraining required\n"
                "• Manual review before resuming"
            )
        )
        return await self.send_alert(message, level="warning" if drift_level == "YELLOW" else "critical")

    async def send_performance_report(
        self,
        daily_ic: float,
        icir: float,
        model_weights: dict[str, float],
        psi_90d: float,
        pnl_today: float | None = None,
    ) -> bool:
        """
        Send daily performance report.

        Args:
            daily_ic: Daily composite IC
            icir: ICIR (IC / std)
            model_weights: Current model weights
            psi_90d: PSI 90-day value
            pnl_today: Optional P&L for today
        """
        weights_str = "\n".join(
            f"• {k}: {v:.1%}" for k, v in sorted(model_weights.items())
        )

        message = (
            f"<b>📊 Daily Performance Report</b>\n\n"
            f"<b>IC Metrics:</b>\n"
            f"• Composite IC: <b>{daily_ic:.4f}</b>\n"
            f"• ICIR: <b>{icir:.3f}</b>\n"
            + (f"• P&L Today: <b>{pnl_today:+.2f}%</b>\n" if pnl_today is not None else "")
            + f"\n<b>Model Weights:</b>\n{weights_str}\n\n"
            f"<b>Drift:</b>\n"
            f"• PSI (90d): {psi_90d:.4f}\n\n"
            f"<i>Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
        )
        return await self.send_alert(message, level="info")

    async def send_message_with_keyboard(
        self,
        message: str,
        keyboard: list[list[dict]],
        parse_mode: str = "HTML",
    ) -> int | None:
        """
        Send message with InlineKeyboardMarkup.

        Args:
            message: Message text (supports HTML markup)
            keyboard: Inline keyboard layout [[{"text": "Btn", "callback_data": "data"}]]
            parse_mode: Parse mode ("HTML" or "Markdown")

        Returns:
            message_id if sent successfully, None if disabled or failed
        """
        if not self._enabled:
            print(f"TelegramNotifier: Disabled (no bot_token/chat_id)")
            return None

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                        "reply_markup": {"inline_keyboard": keyboard},
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("result", {}).get("message_id")
        except Exception as e:
            print(f"TelegramNotifier: Failed to send message with keyboard: {e}")
            return None

    async def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        keyboard: list[list[dict]] | None = None,
    ) -> bool:
        """
        Edit reply markup of an existing message.

        Args:
            chat_id: Channel or user ID
            message_id: Message ID to edit
            keyboard: New inline keyboard. None removes the keyboard entirely.

        Returns:
            True if successful, False otherwise
        """
        if not self._enabled:
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/editMessageReplyMarkup"

        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"TelegramNotifier: Failed to edit reply markup: {e}")
            return False


def format_fallback_alert(count: int) -> str:
    """Format fallback alert message for Telegram."""
    return (
        f"⚠️ <b>Ensemble Fallback Alert</b>\n\n"
        f"Consecutive fallbacks: <b>{count}</b>/{config.MAX_CONSECUTIVE_FALLBACKS}\n"
        f"Position sizing: 50%"
    )


def format_performance_report(
    daily_ic: float,
    icir: float,
    model_weights: dict,
    psi_90d: float,
    pnl_today: float | None = None,
) -> str:
    """Format performance report for Telegram."""
    weights_str = "\n".join(
        f"• {k}: {v:.1%}" for k, v in sorted(model_weights.items())
    )

    return (
        f"📊 <b>Daily Performance Report</b>\n\n"
        f"IC: {daily_ic:.4f} | ICIR: {icir:.3f}\n"
        + (f"P&L: {pnl_today:+.2f}%\n" if pnl_today is not None else "")
        + f"\nWeights:\n{weights_str}\n\n"
        f"PSI(90d): {psi_90d:.4f}"
    )


# Threshold for displaying weight delta as percentage vs "= "
_DELTA_DISPLAY_THRESHOLD = 0.005  # 0.5%


def format_auto_apply_message(
    new_weights: dict[str, float],
    current_weights: dict[str, float],
    guardrail_values: dict[str, float],
    next_review_date: date,
) -> str:
    """Format Telegram message for successful auto-apply."""
    lines = ["✅ <b>Pesi aggiornati automaticamente</b>\n", "📊 <b>Nuovi pesi:</b>"]
    for model, w in sorted(new_weights.items()):
        old_w = current_weights.get(model, 0.0)
        delta = w - old_w
        delta_str = f" ({delta:+.0%})" if abs(delta) >= _DELTA_DISPLAY_THRESHOLD else " (=)"
        lines.append(f"  {model}: {w:.0%}{delta_str}")

    lines.append("\n🛡️ <b>Guardrail superati:</b>")
    if "vix" in guardrail_values:
        lines.append(f"  VIX: {guardrail_values['vix']:.1f}")
    if "ic_variance" in guardrail_values:
        lines.append(f"  IC variance: {guardrail_values['ic_variance']:.3f}")
    if "weight_delta_max" in guardrail_values:
        lines.append(f"  Δmax peso: {guardrail_values['weight_delta_max']:.0%}")

    lines.append(f"\n🕐 Prossima revisione: {next_review_date}")
    return "\n".join(lines)


def format_freeze_message(
    suggested_weights: dict[str, float],
    current_weights: dict[str, float],
    freeze_reason: str,
) -> str:
    """Format Telegram message for frozen auto-apply."""
    lines = [
        "⚠️ <b>Auto-apply bloccato — approvazione manuale richiesta</b>\n",
        f"🚫 <b>Guardrail fallito:</b> {freeze_reason}\n",
        "📊 <b>Pesi suggeriti (NON applicati):</b>",
    ]
    for model, w in sorted(suggested_weights.items()):
        old_w = current_weights.get(model, 0.0)
        delta = w - old_w
        delta_str = f" ({delta:+.0%})" if abs(delta) >= _DELTA_DISPLAY_THRESHOLD else " (=)"
        lines.append(f"  {model}: {w:.0%}{delta_str}")

    lines.append("\n👉 Approva manualmente: POST /api/weights/approve")
    return "\n".join(lines)


def format_freeze_message_with_keyboard(
    suggested_weights: dict[str, float],
    current_weights: dict[str, float],
    freeze_reason: str,
    suggestion_token: str,
) -> tuple[str, list[list[dict]]]:
    """
    Format Telegram freeze message with inline keyboard.

    Args:
        suggested_weights: New weights suggested by performance worker
        current_weights: Current active weights
        freeze_reason: Which guardrail blocked auto-apply
        suggestion_token: SHA256(computed_at)[:8] for callback validation

    Returns:
        (message_text, inline_keyboard) tuple
    """
    lines = [
        "⚠️ <b>Auto-apply bloccato — approvazione manuale richiesta</b>\n",
        f"🚫 <b>Guardrail fallito:</b> {freeze_reason}\n",
        "📊 <b>Pesi suggeriti (NON applicati):</b>",
    ]
    for model, w in sorted(suggested_weights.items()):
        old_w = current_weights.get(model, 0.0)
        delta = w - old_w
        delta_str = f" ({delta:+.0%})" if abs(delta) >= _DELTA_DISPLAY_THRESHOLD else " (=)"
        lines.append(f"  {model}: {w:.0%}{delta_str}")

    keyboard = [
        [{"text": "✅ Approva", "callback_data": f"approve:{suggestion_token}"}],
        [{"text": "❌ Rifiuta", "callback_data": f"reject:{suggestion_token}"}],
    ]

    return "\n".join(lines), keyboard


def format_regime_message(
    state: "RegimeState",
    previous_regime: str | None,
    disagreement: bool,
) -> str:
    """Format Telegram message for a regime change notification."""
    from src.models.regime import RegimeState  # type: ignore[name-defined]

    regime_upper = state.regime.upper()
    mult = state.multiplier

    if previous_regime:
        header = f"📊 <b>Regime: {previous_regime.upper()} → {regime_upper}</b> (×{mult})"
    else:
        header = f"📊 <b>Regime iniziale: {regime_upper}</b> (×{mult})"

    snap = state.macro_snapshot
    data_line = (
        f"VIX: {snap.vix:.1f} | T10Y2Y: {snap.yield_curve:.2f}% | SPY 20d: {snap.spy_momentum_20d:+.1f}%"
    )

    lines = [header, data_line]

    if state.llm_outputs:
        reasoning = state.llm_outputs[0].get("reasoning", "")
        if reasoning:
            lines.append(f"Reasoning: {reasoning}")

    if disagreement and len(state.llm_outputs) >= 2:
        r1 = state.llm_outputs[0].get("regime", "?")
        r2 = state.llm_outputs[1].get("regime", "?")
        lines.append(f"⚠️ Disaccordo LLM: {r1} vs {r2} → applico {state.regime}")

    return "\n".join(lines)
