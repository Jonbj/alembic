package com.jonbj.alembic.monitor.feature.events

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
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
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun EventDetailScreen(viewModel: EventDetailViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    when (state) {
        is LoadState.Loading -> LoadingSpinner()
        is LoadState.Error -> ErrorMessage(
            message = (state as LoadState.Error).message,
            retryable = true,
            onRetry = viewModel::refresh
        )
        is LoadState.Success -> EventDetail((state as LoadState.Success).data)
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
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text("${event.severity.name} · ${event.status.name}")
                    event.summary?.let { Text(it) }
                    Text(
                        event.occurredAt
                            .toLocalDateTime(TimeZone.currentSystemDefault())
                            .toString()
                    )
                }
            }
        }
        if (event.history.isNotEmpty()) {
            item {
                Text(
                    stringResource(R.string.event_timeline),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.semantics { heading() }
                )
            }
            items(event.history) { entry ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(entry.state, fontWeight = FontWeight.Bold)
                        Text(
                            entry.at
                                .toLocalDateTime(TimeZone.currentSystemDefault())
                                .toString()
                        )
                    }
                }
            }
        }
    }
}
