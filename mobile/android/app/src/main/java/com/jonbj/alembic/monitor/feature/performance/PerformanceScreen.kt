package com.jonbj.alembic.monitor.feature.performance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Performance
import com.jonbj.alembic.monitor.ui.components.EmptyMessage
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.OfflineBanner
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent

private val PERIODS = listOf("1w", "1m", "3m", "6m", "1y", "all")

@Composable
fun PerformanceScreen(viewModel: PerformanceViewModel) {
    val state by viewModel.state.collectAsState()
    val period by viewModel.selectedPeriod.collectAsState()
    PerformanceContent(
        state = state,
        selectedPeriod = period,
        onPeriodSelected = viewModel::selectPeriod,
        onRetry = { viewModel.refresh(true) }
    )
}

@Composable
private fun PerformanceContent(
    state: LoadState<Performance>,
    selectedPeriod: String,
    onPeriodSelected: (String) -> Unit,
    onRetry: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        PeriodSelector(
            selected = selectedPeriod,
            onSelected = onPeriodSelected,
            modifier = Modifier.fillMaxWidth()
        )
        when (state) {
            is LoadState.Loading -> LoadingSpinner()
            is LoadState.Error -> ErrorMessage(message = state.message, onRetry = onRetry)
            is LoadState.Success -> {
                if (state.source == com.jonbj.alembic.monitor.core.model.DataSource.CACHE) {
                    OfflineBanner()
                }
                PerformanceMetrics(state.data, modifier = Modifier.verticalScroll(rememberScrollState()))
            }
        }
    }
}

@Composable
private fun PeriodSelector(
    selected: String,
    onSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        PERIODS.forEach { period ->
            Button(
                onClick = { onSelected(period) },
                enabled = period != selected
            ) {
                Text(period.uppercase())
            }
        }
    }
}

@Composable
private fun PerformanceMetrics(performance: Performance, modifier: Modifier = Modifier) {
    Card(modifier = modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            MetricRow(
                stringResource(R.string.portfolio_return),
                formatPercent(performance.summary.portfolioReturn)
            )
            MetricRow(
                stringResource(R.string.nav),
                formatMoney(performance.summary.navEnd, performance.currency)
            )
            MetricRow(
                stringResource(R.string.max_drawdown),
                formatPercent(performance.summary.maxDrawdown)
            )
            MetricRow(
                stringResource(R.string.benchmark),
                formatPercent(performance.summary.benchmarkReturn)
            )
            MetricRow(
                stringResource(R.string.alpha),
                formatPercent(performance.summary.alpha)
            )
            MetricRow(
                stringResource(R.string.realized_pnl),
                formatMoney(performance.summary.realizedPnl, performance.currency)
            )
            Text(
                text = "${performance.points.size} punti",
                style = MaterialTheme.typography.labelLarge
            )
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label)
        Text(value)
    }
}
