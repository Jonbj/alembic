package com.jonbj.alembic.monitor.feature.status

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.PauseCircle
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.MarketPhase
import com.jonbj.alembic.monitor.core.model.Mode
import com.jonbj.alembic.monitor.core.model.Operational
import com.jonbj.alembic.monitor.core.model.OperationalState
import com.jonbj.alembic.monitor.core.model.PipelineComponent
import com.jonbj.alembic.monitor.core.model.PipelineStatus
import com.jonbj.alembic.monitor.core.model.Portfolio
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.core.model.StrategyRow
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.FreshnessBanner
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.MetricRow
import com.jonbj.alembic.monitor.ui.components.MonitorCard
import com.jonbj.alembic.monitor.ui.components.PullRefreshContainer
import com.jonbj.alembic.monitor.ui.components.SectionHeading
import com.jonbj.alembic.monitor.ui.components.StatusPill
import com.jonbj.alembic.monitor.ui.components.effectiveOperationalState
import com.jonbj.alembic.monitor.ui.components.formatDataAge
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent
import com.jonbj.alembic.monitor.ui.components.formatSignedMoney

@Composable
fun StatusScreen(viewModel: StatusViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val refreshing by viewModel.isRefreshing.collectAsStateWithLifecycle()
    StatusContent(
        state = state,
        refreshing = refreshing,
        onRefresh = { viewModel.refresh(true) }
    )
}

@Composable
internal fun StatusContent(
    state: LoadState<Snapshot>,
    refreshing: Boolean,
    onRefresh: () -> Unit
) {
    PullRefreshContainer(refreshing = refreshing, onRefresh = onRefresh) {
        when (state) {
            is LoadState.Loading -> LoadingSpinner()
            is LoadState.Error -> ErrorMessage(
                message = state.message,
                retryable = state.retryable,
                onRetry = onRefresh
            )
            is LoadState.Success -> SnapshotList(state)
        }
    }
}

@Composable
private fun SnapshotList(state: LoadState.Success<Snapshot>) {
    val snapshot = state.data
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            FreshnessBanner(
                mode = state.mode,
                asOf = snapshot.asOf,
                dataAgeSeconds = state.dataAgeSeconds
            )
        }
        item { StateBanner(snapshot.operational) }
        item { PortfolioCard(snapshot.portfolio, snapshot.currency) }
        item { PipelineCard(snapshot.pipeline) }
        item { StrategiesCard(snapshot.strategies) }
        if (snapshot.degradations.isNotEmpty()) {
            item {
                InfoCard(
                    title = stringResource(R.string.degradations),
                    lines = snapshot.degradations
                )
            }
        }
    }
}

@Composable
private fun StateBanner(operational: Operational) {
    val state = effectiveOperationalState(operational)
    val label = operationalStateLabel(state)
    val modeText = modeLabel(operational.mode)
    val color = operationalStateColor(state)
    val icon = when (state) {
        OperationalState.OPERATIONAL -> Icons.Rounded.CheckCircle
        OperationalState.DEGRADED -> Icons.Rounded.Warning
        OperationalState.BLOCKED -> Icons.Rounded.Error
        OperationalState.PAUSED -> Icons.Rounded.PauseCircle
    }
    val reason = when {
        operational.mode == Mode.UNKNOWN -> stringResource(R.string.unknown_mode_reason)
        !operational.primaryReason.isNullOrBlank() -> reasonLabel(operational.primaryReason)
        else -> null
    }
    MonitorCard(
        modifier = Modifier
            .fillMaxWidth()
            .semantics {
                contentDescription = listOfNotNull(label, modeText, reason)
                    .joinToString(". ")
            }
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Icon(icon, contentDescription = null, tint = color)
                Text(
                    text = label,
                    style = MaterialTheme.typography.headlineSmall,
                    color = color,
                    modifier = Modifier
                        .weight(1f)
                        .semantics { heading() }
                )
                StatusPill(
                    text = modeText,
                    color = MaterialTheme.colorScheme.secondary
                )
            }
            Text(
                text = marketPhaseLabel(operational.marketPhase),
                style = MaterialTheme.typography.labelLarge
            )
            reason?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (state == OperationalState.OPERATIONAL) {
                        MaterialTheme.colorScheme.onSurface
                    } else {
                        MaterialTheme.colorScheme.error
                    }
                )
            }
            if (operational.activeIncidentCount > 0) {
                Text(
                    text = pluralStringResource(
                        R.plurals.active_incidents,
                        operational.activeIncidentCount,
                        operational.activeIncidentCount
                    ),
                    style = MaterialTheme.typography.labelLarge
                )
            }
        }
    }
}

@Composable
private fun PortfolioCard(portfolio: Portfolio, currency: String) {
    MonitorCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            SectionHeading(stringResource(R.string.portfolio_summary))
            MetricRow(stringResource(R.string.nav), formatMoney(portfolio.nav, currency))
            MetricRow(
                stringResource(R.string.today),
                buildList {
                    portfolio.navChangeToday?.let { add(formatSignedMoney(it, currency)) }
                    portfolio.navReturnToday?.let { add(formatPercent(it)) }
                }.ifEmpty { listOf("Non disponibile") }.joinToString(" · ")
            )
            MetricRow(
                stringResource(R.string.drawdown),
                formatPercentWithLimit(portfolio.currentDrawdown, portfolio.drawdownLimit)
            )
            MetricRow(
                stringResource(R.string.exposure),
                formatPercentWithLimit(portfolio.grossExposure, portfolio.grossExposureLimit)
            )
            MetricRow(
                stringResource(R.string.positions),
                portfolio.openPositions?.toString() ?: stringResource(R.string.not_available)
            )
            MetricRow(
                stringResource(R.string.unrealized_pnl),
                formatSignedMoney(portfolio.unrealizedPnl, currency)
            )
            MetricRow(stringResource(R.string.cash), formatMoney(portfolio.cash, currency))
        }
    }
}

@Composable
private fun PipelineCard(components: List<PipelineComponent>) {
    MonitorCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            SectionHeading(stringResource(R.string.pipeline))
            if (components.isEmpty()) {
                Text(stringResource(R.string.empty_data))
            } else {
                components.forEach { component ->
                    val age = when (component.status) {
                        PipelineStatus.NOT_EXPECTED -> stringResource(R.string.not_expected)
                        PipelineStatus.UNKNOWN -> stringResource(R.string.not_available)
                        else -> formatDataAge(component.ageSeconds)
                    }
                    MetricRow(
                        label = pipelineName(component.name),
                        value = "${pipelineStatusLabel(component.status)} · $age"
                    )
                    if (component.writeable == false) {
                        Text(
                            text = stringResource(R.string.read_only_component),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StrategiesCard(strategies: List<StrategyRow>) {
    MonitorCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            SectionHeading(stringResource(R.string.strategies))
            if (strategies.isEmpty()) {
                Text(stringResource(R.string.empty_data))
            } else {
                strategies.forEach { strategy ->
                    MetricRow(
                        label = "${strategy.id} · ${strategy.mode}",
                        value = "${formatPercent(strategy.allocationPct)} · ${
                            if (strategy.approved) {
                                stringResource(R.string.approved)
                            } else {
                                stringResource(R.string.not_approved)
                            }
                        }"
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoCard(title: String, lines: List<String>) {
    MonitorCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            SectionHeading(title)
            lines.forEach { Text(it) }
        }
    }
}

@Composable
private fun operationalStateLabel(state: OperationalState): String = when (state) {
    OperationalState.OPERATIONAL -> stringResource(R.string.status_operational)
    OperationalState.DEGRADED -> stringResource(R.string.status_degraded)
    OperationalState.BLOCKED -> stringResource(R.string.status_blocked)
    OperationalState.PAUSED -> stringResource(R.string.status_paused)
}

@Composable
private fun operationalStateColor(state: OperationalState): Color = when (state) {
    OperationalState.OPERATIONAL -> MaterialTheme.colorScheme.primary
    OperationalState.DEGRADED -> MaterialTheme.colorScheme.tertiary
    OperationalState.BLOCKED -> MaterialTheme.colorScheme.error
    OperationalState.PAUSED -> MaterialTheme.colorScheme.outline
}

@Composable
private fun modeLabel(mode: Mode): String = when (mode) {
    Mode.PAPER -> "PAPER"
    Mode.LIVE -> "LIVE"
    Mode.UNKNOWN -> stringResource(R.string.unknown)
}

@Composable
private fun marketPhaseLabel(phase: MarketPhase): String = when (phase) {
    MarketPhase.OPEN -> stringResource(R.string.market_open)
    MarketPhase.PRE_MARKET -> stringResource(R.string.market_pre)
    MarketPhase.AFTER_HOURS -> stringResource(R.string.market_after)
    MarketPhase.CLOSED -> stringResource(R.string.market_closed)
    MarketPhase.HOLIDAY -> stringResource(R.string.market_holiday)
}

@Composable
private fun pipelineStatusLabel(status: PipelineStatus): String = when (status) {
    PipelineStatus.FRESH -> stringResource(R.string.pipeline_fresh)
    PipelineStatus.AGING -> stringResource(R.string.pipeline_aging)
    PipelineStatus.STALE -> stringResource(R.string.pipeline_stale)
    PipelineStatus.NOT_EXPECTED -> stringResource(R.string.not_expected)
    PipelineStatus.UNKNOWN -> stringResource(R.string.unknown)
}

private fun pipelineName(name: String): String =
    when (name.lowercase()) {
        "database" -> "Database"
        "redis" -> "Redis"
        "signal" -> "Segnali"
        "portfolio_cycle" -> "Ciclo portafoglio"
        "broker" -> "Broker"
        else -> name.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }

private fun reasonLabel(reason: String): String = when (reason.lowercase()) {
    "killswitch_active" -> "Kill switch attivo"
    "active_incidents" -> "Incidenti critici attivi"
    "pipeline_degradation" -> "Pipeline degradata"
    "pipeline_not_expected" -> "Pipeline non attesa nella finestra corrente"
    else -> reason.replace('_', ' ').replaceFirstChar { it.uppercase() }
}

private fun formatPercentWithLimit(value: Double?, limit: Double?): String {
    val values = buildList {
        value?.let { add(formatPercent(it)) }
        limit?.let { add(formatPercent(it)) }
    }
    return if (values.isEmpty()) "Non disponibile" else values.joinToString(" / ")
}
