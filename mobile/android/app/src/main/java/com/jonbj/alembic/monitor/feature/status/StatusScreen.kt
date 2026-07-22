package com.jonbj.alembic.monitor.feature.status

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.OperationalState
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.ui.components.EmptyMessage
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.OfflineBanner
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun StatusScreen(viewModel: StatusViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    StatusContent(state = state, onRetry = { viewModel.refresh(true) })
}

@Composable
private fun StatusContent(state: LoadState<Snapshot>, onRetry: () -> Unit) {
    when (state) {
        is LoadState.Loading -> LoadingSpinner()
        is LoadState.Error -> ErrorMessage(
            message = state.message,
            onRetry = onRetry
        )
        is LoadState.Success -> {
            if (state.source == com.jonbj.alembic.monitor.core.model.DataSource.CACHE) {
                OfflineBanner()
            }
            SnapshotCard(state.data, modifier = Modifier.verticalScroll(rememberScrollState()))
        }
    }
}

@Composable
private fun SnapshotCard(snapshot: Snapshot, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        StateBanner(snapshot.operational.state, snapshot.operational.mode.name)
        Text(
            text = stringResource(
                R.string.updated,
                snapshot.asOf.toLocalDateTime(TimeZone.currentSystemDefault()).toString()
            ),
            style = MaterialTheme.typography.labelLarge
        )
        PortfolioCard(snapshot.portfolio, snapshot.currency)
        PipelineCard(snapshot.pipeline)
        StrategiesCard(snapshot.strategies)
    }
}

@Composable
private fun StateBanner(state: OperationalState, mode: String) {
    val (label, color) = when (state) {
        OperationalState.OPERATIONAL -> stringResource(R.string.status_operational) to MaterialTheme.colorScheme.primary
        OperationalState.DEGRADED -> stringResource(R.string.status_degraded) to MaterialTheme.colorScheme.error
        OperationalState.BLOCKED -> stringResource(R.string.status_blocked) to MaterialTheme.colorScheme.error
        OperationalState.PAUSED -> stringResource(R.string.status_paused) to MaterialTheme.colorScheme.outline
    }
    Card {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.headlineMedium,
                color = color
            )
            Text(
                text = mode.uppercase(),
                style = MaterialTheme.typography.titleLarge
            )
        }
    }
}

@Composable
private fun PortfolioCard(portfolio: com.jonbj.alembic.monitor.core.model.Portfolio, currency: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            MetricRow(stringResource(R.string.nav), formatMoney(portfolio.nav, currency))
            MetricRow(stringResource(R.string.today), formatMoney(portfolio.navChangeToday, currency))
            MetricRow(
                stringResource(R.string.drawdown),
                formatPercent(portfolio.currentDrawdown)
            )
            MetricRow(
                stringResource(R.string.exposure),
                formatPercent(portfolio.grossExposure)
            )
            MetricRow(
                stringResource(R.string.positions),
                portfolio.openPositions.toString()
            )
        }
    }
}

@Composable
private fun PipelineCard(components: List<com.jonbj.alembic.monitor.core.model.PipelineComponent>) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = stringResource(R.string.pipeline),
                style = MaterialTheme.typography.titleLarge
            )
            Spacer(modifier = Modifier.height(8.dp))
            components.forEach { component ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(component.name)
                    Text(component.status.name)
                }
            }
        }
    }
}

@Composable
private fun StrategiesCard(strategies: List<com.jonbj.alembic.monitor.core.model.StrategyRow>) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = stringResource(R.string.strategies),
                style = MaterialTheme.typography.titleLarge
            )
            Spacer(modifier = Modifier.height(8.dp))
            strategies.forEach { strategy ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("${strategy.id} (${strategy.mode})")
                    Text(formatPercent(strategy.allocationPct))
                }
            }
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
