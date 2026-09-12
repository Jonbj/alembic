"""Misura point-in-time degli intenti S4 che inseguono il movimento (#512).

Il modulo non decide ordini. Trasforma soltanto lo snapshot Alpaca disponibile
al ciclo in campi persistibili e in un flag ombra.
"""

from __future__ import annotations

from typing import Any

# Soglia osservazionale gia' dichiarata da #327: quartile alto del range della
# seduta. Qui e' accoppiata al segno del movimento dall'apertura, per non
# confondere un prezzo vicino al minimo durante un ribasso con un ingresso
# precoce. Non entra nel money path e non sopprime ordini (freeze #171).
SHADOW_LATE_ENTRY_PERCENTILE = 0.75


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def observe_late_entry(
    *,
    signal_score: float | None,
    decision_price: float | None,
    session_open: float | None,
    session_high: float | None,
    session_low: float | None,
    price_source: str | None,
    threshold: float = SHADOW_LATE_ENTRY_PERCENTILE,
) -> dict[str, Any]:
    """Calcola la posizione del prezzo nel range della seduta disponibile finora.

    ``shadow_late_entry`` ha tre stati: ``True`` quando un long positivo sta
    inseguendo un rialzo nel quartile alto, ``False`` quando i dati escludono il
    predicato, ``None`` quando servirebbe un range che non e' osservabile.
    """
    price = _positive_float(decision_price)
    opening = _positive_float(session_open)
    high = _positive_float(session_high)
    low = _positive_float(session_low)
    missingness: dict[str, str] = {}

    if price is None:
        missingness["decision_price"] = "alpaca_snapshot_price_missing"
    if opening is None:
        missingness["session_open"] = "alpaca_daily_bar_open_missing"

    session_return = None
    if price is not None and opening is not None:
        session_return = price / opening - 1.0

    percentile = None
    if high is None or low is None or high <= low:
        missingness["session_range_percentile"] = "session_range_not_positive"
    elif price is not None:
        percentile = (price - low) / (high - low)

    shadow: bool | None
    reason: str | None = None
    if signal_score is None:
        missingness["signal_score"] = "signal_score_missing"
        shadow = None
    elif signal_score <= 0 or (session_return is not None and session_return < 0):
        shadow = False
    elif session_return is None or percentile is None:
        shadow = None
    else:
        shadow = percentile >= threshold
        if shadow:
            reason = (
                "SHADOW_LATE_ENTRY: "
                f"score={signal_score:+.4g}, ritorno_da_open={session_return:+.4g}, "
                f"percentile_range_finora={percentile:.4g} >= {threshold:.4g}"
            )

    return {
        "decision_price": price,
        "price_source": price_source,
        "session_open": opening,
        "session_high_so_far": high,
        "session_low_so_far": low,
        "session_return_from_open": session_return,
        "session_range_percentile": percentile,
        "shadow_late_entry_threshold": threshold,
        "shadow_late_entry": shadow,
        "shadow_reason": reason,
        "missingness": dict(sorted(missingness.items())),
    }
