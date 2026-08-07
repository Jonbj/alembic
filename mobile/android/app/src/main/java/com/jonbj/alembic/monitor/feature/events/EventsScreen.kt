package com.jonbj.alembic.monitor.feature.events

import android.content.Intent
import android.provider.Settings
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
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
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.EventSeverity
import com.jonbj.alembic.monitor.core.model.EventStatus
import com.jonbj.alembic.monitor.core.model.EventsPage
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.push.PushStatus
import com.jonbj.alembic.monitor.ui.components.EmptyMessage
import com.jonbj.alembic.monitor.ui.components.ErrorMessage
import com.jonbj.alembic.monitor.ui.components.LoadingSpinner
import com.jonbj.alembic.monitor.ui.components.MonitorCard
import com.jonbj.alembic.monitor.ui.components.OfflineBanner
import com.jonbj.alembic.monitor.ui.components.PullRefreshContainer
import com.jonbj.alembic.monitor.ui.components.StatusPill
import com.jonbj.alembic.monitor.ui.components.formatDateTime

@Composable
fun EventsScreen(
    viewModel: EventsViewModel,
    pushStatus: PushStatus,
    onEventSelected: (String) -> Unit
) {
    val context = LocalContext.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    val category by viewModel.selectedCategory.collectAsStateWithLifecycle()
    val days by viewModel.selectedDays.collectAsStateWithLifecycle()
    val refreshing by viewModel.isRefreshing.collectAsStateWithLifecycle()
    val loadingNext by viewModel.isLoadingNext.collectAsStateWithLifecycle()
    EventsContent(
        state = state,
        selectedCategory = category,
        selectedDays = days,
        refreshing = refreshing,
        loadingNext = loadingNext,
        pushStatus = pushStatus,
        onCategorySelected = viewModel::selectCategory,
        onDaysSelected = viewModel::selectDays,
        onEventSelected = onEventSelected,
        onLoadNext = viewModel::loadNext,
        onRetry = { viewModel.refresh(true) },
        onManageNotifications = {
            context.startActivity(
                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(
                    Settings.EXTRA_APP_PACKAGE,
                    context.packageName
                )
            )
        }
    )
}

@Composable
internal fun EventsContent(
    state: LoadState<EventsPage>,
    selectedCategory: EventFilter,
    selectedDays: Int,
    refreshing: Boolean,
    loadingNext: Boolean,
    pushStatus: PushStatus,
    onCategorySelected: (EventFilter) -> Unit,
    onDaysSelected: (Int) -> Unit,
    onEventSelected: (String) -> Unit,
    onLoadNext: () -> Unit,
    onRetry: () -> Unit,
    onManageNotifications: () -> Unit = {}
) {
    PullRefreshContainer(refreshing = refreshing, onRefresh = onRetry) {
        Column(modifier = Modifier.fillMaxSize()) {
            EventFilters(
                selectedCategory,
                selectedDays,
                pushStatus,
                onCategorySelected,
                onDaysSelected,
                onManageNotifications
            )
            when (state) {
                is LoadState.Loading -> LoadingSpinner()
                is LoadState.Error -> ErrorMessage(
                    message = state.message,
                    retryable = state.retryable,
                    onRetry = onRetry
                )
                is LoadState.Success -> {
                    if (state.source == com.jonbj.alembic.monitor.core.model.DataSource.CACHE) {
                        OfflineBanner()
                    }
                    EventsList(
                        state.data,
                        loadingNext,
                        onEventSelected,
                        onLoadNext
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EventFilters(
    selectedCategory: EventFilter,
    selectedDays: Int,
    pushStatus: PushStatus,
    onCategorySelected: (EventFilter) -> Unit,
    onDaysSelected: (Int) -> Unit,
    onManageNotifications: () -> Unit
) {
    Column(
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(
                Icons.Rounded.NotificationsActive,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary
            )
            Text(
                text = when (pushStatus) {
                    PushStatus.ENABLED -> stringResource(R.string.push_enabled)
                    PushStatus.REGISTERING -> stringResource(R.string.push_registering)
                    PushStatus.UNAVAILABLE -> stringResource(R.string.push_unavailable)
                    PushStatus.ERROR -> stringResource(R.string.push_error)
                    PushStatus.DISABLED -> stringResource(R.string.push_disabled)
                },
                style = MaterialTheme.typography.labelLarge
            )
        }
        if (pushStatus == PushStatus.DISABLED) {
            TextButton(onClick = onManageNotifications) {
                Text(stringResource(R.string.push_manage))
            }
        }
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            EventFilter.entries.forEach { filter ->
                FilterChip(
                    selected = filter == selectedCategory,
                    onClick = { onCategorySelected(filter) },
                    label = {
                        Text(
                            stringResource(
                                when (filter) {
                                    EventFilter.ALL -> R.string.filter_all
                                    EventFilter.CRITICAL -> R.string.filter_critical
                                    EventFilter.TRADING -> R.string.filter_trading
                                    EventFilter.SYSTEM -> R.string.filter_system
                                }
                            )
                        )
                    }
                )
            }
        }
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            listOf(7, 30).forEach { days ->
                FilterChip(
                    selected = days == selectedDays,
                    onClick = { onDaysSelected(days) },
                    label = {
                        Text(
                            stringResource(
                                if (days == 7) R.string.events_days_7
                                else R.string.events_days_30
                            )
                        )
                    }
                )
            }
        }
    }
}

@Composable
private fun EventsList(
    page: EventsPage,
    loadingNext: Boolean,
    onEventSelected: (String) -> Unit,
    onLoadNext: () -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(16.dp)
    ) {
        if (page.items.isEmpty()) {
            item { EmptyMessage(Modifier.fillMaxWidth().heightIn(min = 160.dp)) }
        } else {
            items(page.items, key = { it.id }) { event ->
                EventCard(event) { onEventSelected(event.id) }
            }
        }
        if (page.nextCursor != null) {
            item {
                androidx.compose.material3.Button(
                    onClick = onLoadNext,
                    enabled = !loadingNext,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        stringResource(
                            if (loadingNext) R.string.loading_more
                            else R.string.load_more
                        )
                    )
                }
            }
        }
    }
}

@Composable
private fun EventCard(event: EventItem, onClick: () -> Unit) {
    val localTime = formatDateTime(event.occurredAt)
    val severity = eventSeverityLabel(event.severity)
    val status = eventStatusLabel(event.status)
    val severityColor = eventSeverityColor(event.severity)
    MonitorCard(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .semantics {
                role = Role.Button
                contentDescription =
                    "${event.title}. $severity. $status. $localTime"
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
                    text = event.title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f).semantics { heading() }
                )
                StatusPill(text = severity, color = severityColor)
            }
            event.summary?.takeIf { it.isNotBlank() }?.let { Text(it) }
            Text(
                "$status · $localTime",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (event.history.isNotEmpty()) {
                Text(
                    text = stringResource(
                        R.string.event_history_count,
                        event.history.size
                    ),
                    style = MaterialTheme.typography.labelLarge
                )
            }
        }
    }
}

@Composable
internal fun eventSeverityLabel(severity: EventSeverity): String = stringResource(
    when (severity) {
        EventSeverity.CRITICAL -> R.string.event_severity_critical
        EventSeverity.WARNING -> R.string.event_severity_warning
        EventSeverity.INFO -> R.string.event_severity_info
    }
)

@Composable
internal fun eventStatusLabel(status: EventStatus): String = stringResource(
    when (status) {
        EventStatus.OPEN -> R.string.event_status_open
        EventStatus.ESCALATED -> R.string.event_status_escalated
        EventStatus.RECOVERED -> R.string.event_status_recovered
        EventStatus.CLOSED -> R.string.event_status_closed
    }
)

@Composable
internal fun eventSeverityColor(severity: EventSeverity) = when (severity) {
    EventSeverity.CRITICAL -> MaterialTheme.colorScheme.error
    EventSeverity.WARNING -> MaterialTheme.colorScheme.tertiary
    EventSeverity.INFO -> MaterialTheme.colorScheme.secondary
}

@Composable
internal fun eventHistoryStateLabel(state: String): String = when (state.lowercase()) {
    "open" -> stringResource(R.string.event_status_open)
    "escalated" -> stringResource(R.string.event_status_escalated)
    "recovered" -> stringResource(R.string.event_status_recovered)
    "closed", "resolved" -> stringResource(R.string.event_status_closed)
    else -> state.replace('_', ' ').replaceFirstChar { it.uppercase() }
}
