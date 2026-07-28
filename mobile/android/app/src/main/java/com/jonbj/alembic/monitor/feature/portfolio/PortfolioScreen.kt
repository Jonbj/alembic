package com.jonbj.alembic.monitor.feature.portfolio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.jonbj.alembic.monitor.core.model.Position
import com.jonbj.alembic.monitor.core.model.Positions
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.OfflineBanner
import com.jonbj.alembic.monitor.ui.components.formatMoney
import com.jonbj.alembic.monitor.ui.components.formatPercent

@Composable
fun PortfolioScreen(viewModel: PortfolioViewModel) {
    val state by viewModel.state.collectAsState()
    PortfolioContent(state = state, onRetry = { viewModel.refresh(true) })
}

@Composable
private fun PortfolioContent(state: LoadState<Positions>, onRetry: () -> Unit) {
    when (state) {
        is LoadState.Loading -> LoadingSpinner()
        is LoadState.Error -> ErrorMessage(message = state.message, onRetry = onRetry)
        is LoadState.Success -> {
            if (state.source == com.jonbj.alembic.monitor.core.model.DataSource.CACHE) {
                OfflineBanner()
            }
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp)
            ) {
                item {
                    SummaryCard(state.data.summary, state.data.currency)
                }
                items(state.data.items.sortedByDescending { it.unrealizedReturn }) { position ->
                    PositionCard(position, state.data.currency)
                }
            }
        }
    }
}

@Composable
private fun SummaryCard(summary: com.jonbj.alembic.monitor.core.model.PositionSummary, currency: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            MetricRow(stringResource(R.string.positions), summary.count.toString())
            MetricRow(stringResource(R.string.market_value), formatMoney(summary.marketValue, currency))
            MetricRow(stringResource(R.string.unrealized_pnl), formatMoney(summary.unrealizedPnl, currency))
            MetricRow(stringResource(R.string.exposure), formatPercent(summary.grossExposure))
        }
    }
}

@Composable
private fun PositionCard(position: Position, currency: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = position.symbol,
                    style = MaterialTheme.typography.titleLarge
                )
                Text(formatPercent(position.unrealizedReturn))
            }
            MetricRow(stringResource(R.string.market_value), formatMoney(position.marketValue, currency))
            MetricRow(stringResource(R.string.unrealized_pnl), formatMoney(position.unrealizedPnl, currency))
            MetricRow(stringResource(R.string.position_weight), formatPercent(position.positionWeight))
            MetricRow(stringResource(R.string.quantity), "%.4f".format(position.qty))
            MetricRow(stringResource(R.string.current_price), formatMoney(position.currentPrice, currency))
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label, style = MaterialTheme.typography.bodyLarge)
        Text(value)
    }
}
