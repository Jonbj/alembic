"""Telegram notifications for trading system alerts.

Module-level format helpers (pure functions, return str or tuple[str, list]):
    format_fallback_alert(count)
    format_performance_report(daily_ic, icir, model_weights, psi_90d, pnl_today)
    format_auto_apply_message(new_weights, current_weights, guardrail_values, next_review_date)
    format_freeze_message(suggested_weights, current_weights, freeze_reason)
    format_freeze_message_with_keyboard(suggested_weights, current_weights, freeze_reason, token)
        → (message_text, keyboard_layout)  # used by check_and_apply_weights()
    format_regime_message(state, previous_regime, disagreement)

TelegramNotifier class: async HTTP client wrapping the Telegram Bot API.
"""

import json
from datetime import date, datetime, timezone

import httpx

from src.config import config


class TelegramNotifier:
    """
    Async Telegram client for all system notifications.

    Alert methods (all async, return True on success):
        send_alert(message, level)     — generic alert with level prefix emoji
        send_fallback_alert(count)     — ensemble fallback circuit breaker reached
        send_killswitch_alert(reason)  — kill-switch activated
        send_budget_alert(spent, limit)— LLM daily budget exhausted
        send_drift_alert(level, psi)   — PSI/CUSUM drift detected
        send_performance_report(...)   — daily IC/ICIR/weights summary

    Inline keyboard methods (for Telegram approval flow):
        send_message_with_keyboard(message, keyboard) → message_id | None
            Sends message with InlineKeyboardMarkup (✅/❌ buttons).
            Returns message_id needed for later editMessageReplyMarkup.

        edit_message_reply_markup(chat_id, message_id, keyboard=None) → bool
            Removes or replaces inline keyboard after user taps a button.
            Pass keyboard=None to remove all buttons.

    Usage:
        notifier = TelegramNotifier()

        # Simple alert
        await notifier.send_alert("Kill-switch activated: VIX spike detected", level="critical")

        # Freeze notification with approval buttons
        msg, keyboard = format_freeze_message_with_keyboard(weights, current, reason, token)
        message_id = await notifier.send_message_with_keyboard(msg, keyboard)

    Note:
        All methods silently return False/None if bot_token or chat_id are not configured,
        making Telegram optional in development environments.
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
        Send Telegram message with InlineKeyboardMarkup (inline buttons).

        Used for the approval flow: when guardrails block auto-apply of new
        ensemble weights, this sends a freeze notification with ✅/❌ buttons.

        Keyboard format (Telegram InlineKeyboardMarkup):
            [
                [{"text": "✅ Approva", "callback_data": "approve:abc12345"}],
                [{"text": "❌ Rifiuta", "callback_data": "reject:abc12345"}]
            ]

        Each inner list is a row. callback_data is echoed back in callback_query
        when user taps — it's validated by telegram_poller.py.

        Args:
            message: Message text (supports HTML markup if parse_mode="HTML")
            keyboard: Inline keyboard layout — list of rows, each row is list of buttons
            parse_mode: "HTML" (default) or "Markdown"

        Returns:
            message_id (int) if sent successfully — needed for later editing
            None if disabled (no bot_token/chat_id) or HTTP error

        Note:
            The message_id is NOT persisted. The poller retrieves it from
            callback_query["message"]["message_id"] when user taps a button.
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
        Edit reply markup (inline keyboard) of an existing Telegram message.

        Used after processing an approve/reject tap to remove the keyboard,
        preventing double-taps and confusion.

        Telegram API: editMessageReplyMarkup
        - chat_id: Channel or user ID where message was sent
        - message_id: ID of message to edit
        - keyboard: None removes all buttons; pass new keyboard to replace

        Args:
            chat_id: Channel or user ID (string or int)
            message_id: Message ID to edit
            keyboard: New inline keyboard, or None to remove entirely

        Returns:
            True if successful, False if disabled or HTTP error

        Note:
            This is an async method. In sync Celery tasks, wrap with:
                asyncio.run(notifier.edit_message_reply_markup(...))
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
        else:
            payload["reply_markup"] = {}  # empty object signals Telegram to remove keyboard

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
    Format Telegram freeze message with inline keyboard for approval/rejection.

    This function is called by check_and_apply_weights() in performance.py when
    guardrails block automatic weight updates. It generates:

    1. A formatted message showing:
       - Warning header (⚠️ Auto-apply bloccato)
       - Which guardrail failed (VIX, IC variance, weight delta)
       - Suggested weights vs current weights (with delta %)

    2. An inline keyboard with two buttons:
       - ✅ Approva → callback_data: "approve:<token>"
       - ❌ Rifiuta → callback_data: "reject:<token>"

    The token is validated by telegram_poller.py to prevent replay attacks.

    Design decision: Unlike format_freeze_message(), this does NOT include
    the "👉 Approva manualmente: POST /api/weights/approve" hint because
    the inline keyboard provides direct action.

    Args:
        suggested_weights: Dict of {model_id: weight} proposed by performance worker
        current_weights: Dict of {model_id: weight} currently active in Redis
        freeze_reason: Human-readable guardrail failure reason (e.g., "VIX = 38.2 >= 30.0")
        suggestion_token: 8-char SHA256 hash of computed_at timestamp for anti-replay

    Returns:
        Tuple of (message_text, keyboard_layout):
        - message_text: str with HTML formatting for Telegram
        - keyboard_layout: list of rows, each row is list of button dicts

    Example keyboard output:
        [
            [{"text": "✅ Approva", "callback_data": "approve:abc12345"}],
            [{"text": "❌ Rifiuta", "callback_data": "reject:abc12345"}]
        ]
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
