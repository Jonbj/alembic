package com.jonbj.alembic.monitor.feature.events

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.EventsPage
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.OfflineBanner
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

private val CATEGORIES = listOf("all", "critical", "trading", "system")

@Composable
fun EventsScreen(viewModel: EventsViewModel) {
    val state by viewModel.state.collectAsState()
    val category by viewModel.selectedCategory.collectAsState()
    EventsContent(
        state = state,
        selectedCategory = category,
        onCategorySelected = viewModel::selectCategory,
        onRetry = { viewModel.refresh(true) }
    )
}

@Composable
private fun EventsContent(
    state: LoadState<EventsPage>,
    selectedCategory: String,
    onCategorySelected: (String) -> Unit,
    onRetry: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            CATEGORIES.forEach { category ->
                Button(
                    onClick = { onCategorySelected(category) },
                    enabled = category != selectedCategory
                ) {
                    Text(category.uppercase())
                }
            }
        }
        when (state) {
            is LoadState.Loading -> LoadingSpinner()
            is LoadState.Error -> ErrorMessage(message = state.message, onRetry = onRetry)
            is LoadState.Success -> {
                if (state.source == com.jonbj.alembic.monitor.core.model.DataSource.CACHE) {
                    OfflineBanner()
                }
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.padding(top = 8.dp)
                ) {
                    items(state.data.items) { event ->
                        EventCard(event)
                    }
                }
            }
        }
    }
}

@Composable
private fun EventCard(event: EventItem) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = event.title,
                    style = MaterialTheme.typography.titleMedium
                )
                Text(event.severity.name)
            }
            Text(
                text = event.summary.orEmpty(),
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(vertical = 4.dp)
            )
            Text(
                text = event.occurredAt.toLocalDateTime(TimeZone.currentSystemDefault()).toString(),
                style = MaterialTheme.typography.labelLarge
            )
        }
    }
}
