package com.jonbj.alembic.monitor.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material.ExperimentalMaterialApi
import androidx.compose.material.pullrefresh.PullRefreshIndicator
import androidx.compose.material.pullrefresh.pullRefresh
import androidx.compose.material.pullrefresh.rememberPullRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.ContentMode
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import java.text.NumberFormat
import java.util.Locale

@Composable
fun LoadingSpinner(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        CircularProgressIndicator()
    }
}

@Composable
fun ErrorMessage(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    retryable: Boolean = true
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = message,
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center
        )
        if (retryable) {
            Button(onClick = onRetry, modifier = Modifier.padding(top = 16.dp)) {
                Text(text = stringResource(R.string.retry))
            }
        }
    }
}

@Composable
fun EmptyMessage(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = stringResource(R.string.empty_data),
            style = MaterialTheme.typography.bodyLarge
        )
    }
}

@Composable
fun FreshnessBanner(
    mode: ContentMode,
    asOf: Instant,
    dataAgeSeconds: Int,
    modifier: Modifier = Modifier
) {
    val modeLabel = when (mode) {
        ContentMode.LIVE -> stringResource(R.string.live)
        ContentMode.OFFLINE -> stringResource(R.string.offline)
        ContentMode.STALE -> stringResource(R.string.stale)
        ContentMode.INCOMPATIBLE -> stringResource(R.string.version_update_required)
        ContentMode.UNAUTHENTICATED -> stringResource(R.string.session_expired)
        ContentMode.UNAVAILABLE -> stringResource(R.string.unavailable)
    }
    val time = asOf.toLocalDateTime(TimeZone.currentSystemDefault())
    val accent = if (mode == ContentMode.LIVE) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.error
    }
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.medium,
        color = accent.copy(alpha = 0.11f),
        contentColor = accent
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                modifier = Modifier.size(9.dp),
                shape = MaterialTheme.shapes.extraLarge,
                color = accent
            ) {}
            Spacer(Modifier.size(10.dp))
            Text(
                text = modeLabel,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.weight(1f)
            )
            Text(
                text = stringResource(
                    R.string.freshness_compact,
                    "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}",
                    formatDataAge(dataAgeSeconds)
                ),
                style = MaterialTheme.typography.labelMedium,
                color = if (mode == ContentMode.LIVE) {
                    MaterialTheme.colorScheme.onSurfaceVariant
                } else {
                    accent
                },
                textAlign = TextAlign.End
            )
        }
    }
}

@OptIn(ExperimentalMaterialApi::class)
@Composable
fun PullRefreshContainer(
    refreshing: Boolean,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit
) {
    val state = rememberPullRefreshState(refreshing, onRefresh)
    Box(modifier = modifier.fillMaxSize().pullRefresh(state)) {
        content()
        PullRefreshIndicator(
            refreshing = refreshing,
            state = state,
            modifier = Modifier.align(Alignment.TopCenter),
            backgroundColor = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.primary
        )
    }
}

@Composable
fun OfflineBanner(modifier: Modifier = Modifier) {
    Text(
        text = stringResource(R.string.offline),
        modifier = modifier.padding(8.dp)
    )
}

fun formatMoney(
    value: Double?,
    currency: String = "USD",
    orEmpty: String = "Non disponibile"
): String {
    if (value == null) return orEmpty
    return when (currency.uppercase()) {
        "USD" -> NumberFormat.getCurrencyInstance(Locale.US).format(value)
        else -> "%.2f $currency".format(value)
    }
}

fun formatPercent(value: Double?, orEmpty: String = "Non disponibile"): String {
    if (value == null) return orEmpty
    return NumberFormat.getPercentInstance(Locale.US).apply {
        minimumFractionDigits = 2
        maximumFractionDigits = 2
    }.format(value)
}

fun formatDateTime(instant: Instant): String {
    val local = instant.toLocalDateTime(TimeZone.currentSystemDefault())
    return buildString {
        append(local.dayOfMonth.toString().padStart(2, '0'))
        append('/')
        append(local.monthNumber.toString().padStart(2, '0'))
        append('/')
        append(local.year)
        append(" · ")
        append(local.hour.toString().padStart(2, '0'))
        append(':')
        append(local.minute.toString().padStart(2, '0'))
    }
}
