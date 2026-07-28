package com.jonbj.alembic.monitor.ui.components

import com.jonbj.alembic.monitor.core.model.Mode
import com.jonbj.alembic.monitor.core.model.Operational
import com.jonbj.alembic.monitor.core.model.OperationalState
import com.jonbj.alembic.monitor.core.model.Position
import java.math.BigDecimal
import kotlin.math.absoluteValue

fun effectiveOperationalState(operational: Operational): OperationalState =
    if (operational.mode == Mode.UNKNOWN) OperationalState.BLOCKED else operational.state

fun foregroundRefreshIntervalMillis(pipelineExpected: Boolean): Long =
    if (pipelineExpected) 60_000L else 5L * 60_000L

fun sortPositionsForRisk(positions: List<Position>): List<Position> =
    positions.sortedWith(
        compareBy<Position> { it.unrealizedReturn ?: Double.POSITIVE_INFINITY }
            .thenByDescending { it.marketValue?.absoluteValue ?: 0.0 }
    )

fun formatSignedMoney(
    value: Double?,
    currency: String = "USD",
    unavailable: String = "Non disponibile"
): String {
    if (value == null) return unavailable
    val formatted = formatMoney(value, currency, unavailable)
    return if (value > 0.0) "+$formatted" else formatted
}

fun formatQuantity(value: Double?, unavailable: String = "Non disponibile"): String =
    value?.let { BigDecimal.valueOf(it).stripTrailingZeros().toPlainString() } ?: unavailable

fun formatDataAge(ageSeconds: Int?, unavailable: String = "Non disponibile"): String {
    if (ageSeconds == null) return unavailable
    val safeAgeSeconds = ageSeconds.coerceAtLeast(0)
    return when {
        safeAgeSeconds < 60 -> {
            "$safeAgeSeconds ${if (safeAgeSeconds == 1) "secondo" else "secondi"}"
        }
        safeAgeSeconds < 3_600 -> {
            val minutes = safeAgeSeconds / 60
            "$minutes ${if (minutes == 1) "minuto" else "minuti"}"
        }
        else -> {
            val hours = safeAgeSeconds / 3_600
            "$hours ${if (hours == 1) "ora" else "ore"}"
        }
    }
}
