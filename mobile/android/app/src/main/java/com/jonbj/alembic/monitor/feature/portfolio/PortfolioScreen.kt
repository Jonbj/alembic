package com.jonbj.alembic.monitor.feature.portfolio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Position
import com.jonbj.alembic.monitor.core.model.PositionSummary
import com.jonbj.alembic.monitor.core.model.Positions
import com.jonbj.alembic.monitor.ui.components.EmptyMessage
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.FreshnessBanner
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.MetricRow
import com.jonbj.alembic.monitor.ui.components.MonitorCard
import com.jonbj.alembic.monitor.ui.components.PullRefreshContainer
import com.jonbj.alembic.monitor.ui.components.SectionHeading
import com.jonbj.alembic.monitor.ui.components.formatDataAge
import com.jonbj.alembic.monitor.ui.components.formatDateTime
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent
import com.jonbj.alembic.monitor.ui.components.formatQuantity
import com.jonbj.alembic.monitor.ui.components.formatSignedMoney
import com.jonbj.alembic.monitor.ui.components.sortPositionsForRisk

@Composable
fun PortfolioScreen(viewModel: PortfolioViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val refreshing by viewModel.isRefreshing.collectAsStateWithLifecycle()
    PortfolioContent(
        state = state,
        refreshing = refreshing,
        onRefresh = { viewModel.refresh(true) }
    )
}

@Composable
internal fun PortfolioContent(
    state: LoadState<Positions>,
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
            is LoadState.Success -> PositionsList(state)
        }
    }
}

@Composable
private fun PositionsList(state: LoadState.Success<Positions>) {
    val positions = state.data
    var expandedSymbol by rememberSaveable { mutableStateOf<String?>(null) }
    val ordered = sortPositionsForRisk(positions.items)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(16.dp)
    ) {
        item {
            FreshnessBanner(
                mode = state.mode,
                asOf = positions.asOf,
                dataAgeSeconds = state.dataAgeSeconds
            )
        }
        item { SummaryCard(positions.summary, positions.currency) }
        if (ordered.isEmpty()) {
            item {
                EmptyMessage(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 160.dp)
                )
            }
        } else {
            items(ordered, key = { it.symbol }) { position ->
                PositionCard(
                    position = position,
                    currency = positions.currency,
                    dataAgeSeconds = state.dataAgeSeconds,
                    expanded = expandedSymbol == position.symbol,
                    onToggle = {
                        expandedSymbol =
                            if (expandedSymbol == position.symbol) null else position.symbol
                    }
                )
            }
        }
        if (positions.degradations.isNotEmpty()) {
            item {
                MonitorCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        SectionHeading(stringResource(R.string.degradations))
                        positions.degradations.forEach { Text(it) }
                    }
                }
            }
        }
    }
}

@Composable
private fun SummaryCard(summary: PositionSummary, currency: String) {
    MonitorCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            SectionHeading(stringResource(R.string.portfolio_summary))
            MetricRow(stringResource(R.string.positions), summary.count.toString())
            MetricRow(stringResource(R.string.market_value), formatMoney(summary.marketValue, currency))
            MetricRow(
                stringResource(R.string.unrealized_pnl),
                formatSignedMoney(summary.unrealizedPnl, currency)
            )
            MetricRow(stringResource(R.string.exposure), formatPercent(summary.grossExposure))
        }
    }
}

@Composable
private fun PositionCard(
    position: Position,
    currency: String,
    dataAgeSeconds: Int,
    expanded: Boolean,
    onToggle: () -> Unit
) {
    val description = buildString {
        append(position.symbol)
        append(". Peso ${formatPercent(position.positionWeight)}")
        append(". Valore ${formatMoney(position.marketValue, currency)}")
        append(". P e L non realizzato ${formatSignedMoney(position.unrealizedPnl, currency)}")
        append(", ${formatPercent(position.unrealizedReturn)}")
        append(if (expanded) ". Dettagli aperti" else ". Tocca per i dettagli")
    }
    androidx.compose.material3.ElevatedCard(
        onClick = onToggle,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .semantics {
                role = Role.Button
                contentDescription = description
            }
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = position.symbol,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    text = formatPercent(position.unrealizedReturn),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Icon(
                    imageVector = if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                    contentDescription = null
                )
            }
            MetricRow(stringResource(R.string.position_weight), formatPercent(position.positionWeight))
            MetricRow(stringResource(R.string.market_value), formatMoney(position.marketValue, currency))
            MetricRow(
                stringResource(R.string.unrealized_pnl),
                "${formatSignedMoney(position.unrealizedPnl, currency)} · ${
                    formatPercent(position.unrealizedReturn)
                }"
            )
            if (expanded) {
                MetricRow(stringResource(R.string.quantity), formatQuantity(position.qty))
                MetricRow(
                    stringResource(R.string.avg_entry),
                    formatMoney(position.avgEntryPrice, currency)
                )
                MetricRow(
                    stringResource(R.string.current_price),
                    formatMoney(position.currentPrice, currency)
                )
                MetricRow(
                    stringResource(R.string.entry_time),
                    position.entryTime?.let(::formatDateTime)
                        ?: stringResource(R.string.not_available)
                )
                MetricRow(stringResource(R.string.data_age), formatDataAge(dataAgeSeconds))
            }
        }
    }
}
