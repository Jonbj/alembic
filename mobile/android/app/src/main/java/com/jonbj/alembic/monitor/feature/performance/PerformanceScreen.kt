package com.jonbj.alembic.monitor.feature.performance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Performance
import com.jonbj.alembic.monitor.core.model.PerformancePoint
import com.jonbj.alembic.monitor.ui.components.EmptyMessage
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.FreshnessBanner
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.MetricRow
import com.jonbj.alembic.monitor.ui.components.MonitorCard
import com.jonbj.alembic.monitor.ui.components.PullRefreshContainer
import com.jonbj.alembic.monitor.ui.components.SectionHeading
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent
import com.jonbj.alembic.monitor.ui.components.formatSignedMoney
import com.jonbj.alembic.monitor.ui.components.formatDateTime

@Composable
fun PerformanceScreen(viewModel: PerformanceViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val viewModelPeriod by viewModel.selectedPeriod.collectAsStateWithLifecycle()
    val refreshing by viewModel.isRefreshing.collectAsStateWithLifecycle()
    var savedPeriod by rememberSaveable { mutableStateOf(viewModelPeriod.apiValue) }

    LaunchedEffect(savedPeriod) {
        val restored = PerformancePeriod.fromApiValue(savedPeriod)
        if (restored != viewModelPeriod) viewModel.selectPeriod(restored)
    }
    LaunchedEffect(viewModelPeriod) {
        savedPeriod = viewModelPeriod.apiValue
    }

    PerformanceContent(
        state = state,
        selectedPeriod = viewModelPeriod,
        refreshing = refreshing,
        onPeriodSelected = viewModel::selectPeriod,
        onRefresh = { viewModel.refresh(true) }
    )
}

@Composable
internal fun PerformanceContent(
    state: LoadState<Performance>,
    selectedPeriod: PerformancePeriod,
    refreshing: Boolean,
    onPeriodSelected: (PerformancePeriod) -> Unit,
    onRefresh: () -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        PeriodSelector(
            selected = selectedPeriod,
            onSelected = onPeriodSelected,
            modifier = Modifier.fillMaxWidth()
        )
        PullRefreshContainer(
            refreshing = refreshing,
            onRefresh = onRefresh,
            modifier = Modifier.weight(1f)
        ) {
            when (state) {
                is LoadState.Loading -> LoadingSpinner()
                is LoadState.Error -> ErrorMessage(
                    message = state.message,
                    retryable = state.retryable,
                    onRetry = onRefresh
                )
                is LoadState.Success -> PerformanceList(state)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun PeriodSelector(
    selected: PerformancePeriod,
    onSelected: (PerformancePeriod) -> Unit,
    modifier: Modifier = Modifier
) {
    FlowRow(
        modifier = modifier.padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        PerformancePeriod.entries.forEach { period ->
            FilterChip(
                selected = period == selected,
                onClick = { onSelected(period) },
                label = { Text(stringResource(period.labelRes)) },
                modifier = Modifier.heightIn(min = 48.dp)
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PerformanceList(state: LoadState.Success<Performance>) {
    val performance = state.data
    var showBenchmark by rememberSaveable(performance.period) { mutableStateOf(false) }
    var showDrawdown by rememberSaveable(performance.period) { mutableStateOf(false) }
    var showTable by rememberSaveable(performance.period) { mutableStateOf(false) }
    val hasBenchmark = performance.points.any { it.benchmarkNav != null }
    val hasDrawdown = performance.points.any { it.drawdown != null }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            FreshnessBanner(
                mode = state.mode,
                asOf = performance.asOf,
                dataAgeSeconds = state.dataAgeSeconds
            )
        }
        item { SummaryMetrics(performance) }
        if (performance.points.isEmpty()) {
            item { EmptyMessage(modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp)) }
        } else {
            item {
                MonitorCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        SectionHeading(stringResource(R.string.nav_chart))
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            if (hasBenchmark) FilterChip(
                                selected = showBenchmark,
                                onClick = { showBenchmark = !showBenchmark },
                                label = { Text(stringResource(R.string.benchmark)) }
                            )
                            if (hasDrawdown) FilterChip(
                                selected = showDrawdown,
                                onClick = { showDrawdown = !showDrawdown },
                                label = { Text(stringResource(R.string.drawdown)) }
                            )
                        }
                        PerformanceChart(
                            points = performance.points,
                            currency = performance.currency,
                            showBenchmark = showBenchmark,
                            showDrawdown = showDrawdown
                        )
                        Button(onClick = { showTable = !showTable }) {
                            Text(
                                if (showTable) {
                                    stringResource(R.string.hide_data_table)
                                } else {
                                    stringResource(R.string.show_data_table)
                                }
                            )
                        }
                    }
                }
            }
            if (showTable) {
                item { SectionHeading(stringResource(R.string.accessible_data_table)) }
                items(performance.points, key = { it.at.toEpochMilliseconds() }) { point ->
                    PerformancePointRow(point, performance.currency)
                }
            }
        }
        if (performance.degradations.isNotEmpty()) {
            item {
                MonitorCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        SectionHeading(stringResource(R.string.degradations))
                        performance.degradations.forEach { Text(it) }
                    }
                }
            }
        }
    }
}

@Composable
private fun SummaryMetrics(performance: Performance) {
    MonitorCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            SectionHeading(stringResource(R.string.performance_summary))
            MetricRow(
                stringResource(R.string.portfolio_return),
                formatPercent(performance.summary.portfolioReturn)
            )
            MetricRow(
                stringResource(R.string.nav_change),
                formatSignedMoney(performance.summary.navChange, performance.currency)
            )
            MetricRow(
                stringResource(R.string.nav),
                formatMoney(performance.summary.navEnd, performance.currency)
            )
            MetricRow(
                stringResource(R.string.max_drawdown),
                formatPercent(performance.summary.maxDrawdown)
            )
            performance.summary.benchmarkReturn?.let {
                MetricRow(stringResource(R.string.benchmark), formatPercent(it))
            }
            performance.summary.alpha?.let {
                MetricRow(stringResource(R.string.alpha), formatPercent(it))
            }
            MetricRow(
                stringResource(R.string.avg_exposure),
                formatPercent(performance.summary.avgGrossExposure)
            )
        }
    }
    MonitorCard(modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = stringResource(R.string.realized_pnl),
                style = MaterialTheme.typography.labelLarge
            )
            Text(
                text = formatSignedMoney(
                    performance.summary.realizedPnl,
                    performance.currency
                ),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun PerformancePointRow(point: PerformancePoint, currency: String) {
    val local = formatDateTime(point.at)
    val description = buildList {
        add(local)
        add("NAV ${formatMoney(point.nav, currency)}")
        point.benchmarkNav?.let { add("Benchmark ${formatMoney(it, currency)}") }
        point.drawdown?.let { add("Drawdown ${formatPercent(it)}") }
    }.joinToString(". ")
    MonitorCard(
        modifier = Modifier
            .fillMaxWidth()
            .semantics { contentDescription = description }
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(local)
            MetricRow("NAV", formatMoney(point.nav, currency))
            point.benchmarkNav?.let {
                MetricRow(stringResource(R.string.benchmark), formatMoney(it, currency))
            }
            point.drawdown?.let {
                MetricRow(stringResource(R.string.drawdown), formatPercent(it))
            }
        }
    }
}
