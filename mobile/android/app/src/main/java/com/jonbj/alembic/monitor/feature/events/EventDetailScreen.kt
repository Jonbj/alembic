package com.jonbj.alembic.monitor.feature.events

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.MonitorCard
import com.jonbj.alembic.monitor.ui.components.SectionHeading
import com.jonbj.alembic.monitor.ui.components.StatusPill
import com.jonbj.alembic.monitor.ui.components.formatDateTime

@Composable
fun EventDetailScreen(viewModel: EventDetailViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    EventDetailContent(state, viewModel::refresh)
}

@Composable
internal fun EventDetailContent(
    state: LoadState<EventItem>,
    onRetry: () -> Unit
) {
    when (state) {
        is LoadState.Loading -> LoadingSpinner()
        is LoadState.Error -> ErrorMessage(
            message = state.message,
            retryable = true,
            onRetry = onRetry
        )
        is LoadState.Success -> EventDetail(state.data)
    }
}

@Composable
private fun EventDetail(event: EventItem) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(
                event.title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.semantics { heading() }
            )
        }
        item {
            MonitorCard(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    StatusPill(
                        text = eventSeverityLabel(event.severity),
                        color = when (event.severity) {
                            com.jonbj.alembic.monitor.core.model.EventSeverity.CRITICAL ->
                                MaterialTheme.colorScheme.error
                            com.jonbj.alembic.monitor.core.model.EventSeverity.WARNING ->
                                MaterialTheme.colorScheme.tertiary
                            com.jonbj.alembic.monitor.core.model.EventSeverity.INFO ->
                                MaterialTheme.colorScheme.secondary
                        }
                    )
                    Text(
                        eventStatusLabel(event.status),
                        style = MaterialTheme.typography.labelLarge
                    )
                    event.summary?.let { Text(it) }
                    Text(
                        formatDateTime(event.occurredAt),
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
        if (event.history.isNotEmpty()) {
            item {
                SectionHeading(stringResource(R.string.event_timeline))
            }
            items(event.history) { entry ->
                MonitorCard(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(entry.state, fontWeight = FontWeight.Bold)
                        Text(formatDateTime(entry.at))
                    }
                }
            }
        }
    }
}
