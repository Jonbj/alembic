package com.jonbj.alembic.monitor.feature.performance

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jonbj.alembic.monitor.core.model.PerformancePoint
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent

@Composable
internal fun PerformanceChart(
    points: List<PerformancePoint>,
    currency: String,
    showBenchmark: Boolean,
    showDrawdown: Boolean,
    modifier: Modifier = Modifier
) {
    val description = chartDescription(points, currency, showBenchmark, showDrawdown)
    val strokeWidth = with(LocalDensity.current) { 2.5.dp.toPx() }
    val gridWidth = with(LocalDensity.current) { 1.dp.toPx() }
    val navColor = MaterialTheme.colorScheme.primary
    val benchmarkColor = MaterialTheme.colorScheme.secondary
    val drawdownColor = MaterialTheme.colorScheme.tertiary
    val gridColor = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.55f)
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(220.dp)
            .semantics { contentDescription = description }
    ) {
        if (points.size < 2) return@Canvas
        repeat(4) { index ->
            val y = size.height * index / 3f
            drawLine(
                color = gridColor,
                start = Offset(0f, y),
                end = Offset(size.width, y),
                strokeWidth = gridWidth
            )
        }
        drawNormalizedArea(
            values = points.map { it.nav },
            color = navColor
        )
        drawNormalizedLine(
            values = points.map { it.nav },
            color = navColor,
            strokeWidth = strokeWidth
        )
        if (showBenchmark) {
            drawNormalizedLine(
                values = points.map { it.benchmarkNav },
                color = benchmarkColor,
                strokeWidth = strokeWidth
            )
        }
        if (showDrawdown) {
            drawNormalizedLine(
                values = points.map { it.drawdown },
                color = drawdownColor,
                strokeWidth = strokeWidth
            )
        }
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawNormalizedArea(
    values: List<Double?>,
    color: Color
) {
    val finite = values.mapNotNull { it?.takeIf(Double::isFinite) }
    if (finite.size < 2) return
    val min = finite.min()
    val max = finite.max()
    val range = (max - min).takeIf { it > 0.0 } ?: 1.0
    val denominator = (values.size - 1).coerceAtLeast(1)
    val path = Path()
    var firstX = 0f
    var lastX = 0f
    var started = false
    values.forEachIndexed { index, value ->
        if (value == null || !value.isFinite()) return@forEachIndexed
        val x = size.width * index / denominator
        val y = size.height - ((value - min) / range * size.height).toFloat()
        if (!started) {
            firstX = x
            path.moveTo(x, y)
            started = true
        } else {
            path.lineTo(x, y)
        }
        lastX = x
    }
    if (!started) return
    path.lineTo(lastX, size.height)
    path.lineTo(firstX, size.height)
    path.close()
    drawPath(
        path = path,
        brush = Brush.verticalGradient(
            colors = listOf(color.copy(alpha = 0.24f), Color.Transparent)
        )
    )
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawNormalizedLine(
    values: List<Double?>,
    color: Color,
    strokeWidth: Float
) {
    val finite = values.mapNotNull { it?.takeIf(Double::isFinite) }
    if (finite.size < 2) return
    val min = finite.min()
    val max = finite.max()
    val range = (max - min).takeIf { it > 0.0 } ?: 1.0
    val denominator = (values.size - 1).coerceAtLeast(1)
    val path = Path()
    var started = false
    values.forEachIndexed { index, value ->
        if (value == null || !value.isFinite()) {
            started = false
            return@forEachIndexed
        }
        val x = size.width * index / denominator
        val y = size.height - ((value - min) / range * size.height).toFloat()
        if (!started) {
            path.moveTo(x, y)
            started = true
        } else {
            path.lineTo(x, y)
        }
    }
    drawPath(path, color = color, style = Stroke(width = strokeWidth))
}

private fun chartDescription(
    points: List<PerformancePoint>,
    currency: String,
    showBenchmark: Boolean,
    showDrawdown: Boolean
): String {
    if (points.isEmpty()) return "Grafico senza dati"
    val first = points.first()
    val last = points.last()
    val overlays = buildList {
        if (showBenchmark) add("benchmark")
        if (showDrawdown) add("drawdown")
    }
    return buildString {
        append("Grafico NAV con ${points.size} punti")
        if (overlays.isNotEmpty()) append(", overlay ${overlays.joinToString(" e ")}")
        append(". Da ${formatMoney(first.nav, currency)} a ${formatMoney(last.nav, currency)}")
        last.drawdown?.let { append(". Drawdown finale ${formatPercent(it)}") }
    }
}
