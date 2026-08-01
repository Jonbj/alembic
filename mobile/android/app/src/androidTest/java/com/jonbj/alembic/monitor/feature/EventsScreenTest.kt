package com.jonbj.alembic.monitor.feature

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.Density
import com.jonbj.alembic.monitor.core.model.DataSource
import com.jonbj.alembic.monitor.core.model.EventCategory
import com.jonbj.alembic.monitor.core.model.EventHistoryEntry
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.EventKind
import com.jonbj.alembic.monitor.core.model.EventSeverity
import com.jonbj.alembic.monitor.core.model.EventStatus
import com.jonbj.alembic.monitor.core.model.EventsPage
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.feature.events.EventFilter
import com.jonbj.alembic.monitor.feature.events.EventDetailContent
import com.jonbj.alembic.monitor.feature.events.EventsContent
import com.jonbj.alembic.monitor.push.PushStatus
import com.jonbj.alembic.monitor.ui.theme.AlembicMonitorTheme
import kotlinx.datetime.Clock
import org.junit.Rule
import org.junit.Test

class EventsScreenTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun feedShowsFiltersPushStateIncidentAndPagination() {
        val now = Clock.System.now()
        val event = EventItem(
            id = "event-one",
            kind = EventKind.ALERT_INCIDENT,
            category = EventCategory.CRITICAL,
            severity = EventSeverity.CRITICAL,
            status = EventStatus.RECOVERED,
            occurredAt = now,
            updatedAt = now,
            resolvedAt = now,
            title = "Pipeline dati",
            summary = "Incidente ripristinato",
            entity = null,
            measure = null,
            history = listOf(
                EventHistoryEntry("open", now),
                EventHistoryEntry("recovered", now)
            )
        )
        composeRule.setContent {
            AlembicMonitorTheme {
                EventsContent(
                    state = LoadState.Success(
                        EventsPage(1, now, listOf(event), "opaque"),
                        DataSource.NETWORK,
                        0
                    ),
                    selectedCategory = EventFilter.ALL,
                    selectedDays = 7,
                    refreshing = false,
                    loadingNext = false,
                    pushStatus = PushStatus.ENABLED,
                    onCategorySelected = {},
                    onDaysSelected = {},
                    onEventSelected = {},
                    onLoadNext = {},
                    onRetry = {}
                )
            }
        }

        composeRule.onNodeWithText("Notifiche attive").assertIsDisplayed()
        composeRule.onNodeWithText("Tutti").assertIsDisplayed()
        composeRule.onNodeWithText("7 giorni").assertIsDisplayed()
        composeRule.onNodeWithText("Pipeline dati").assertIsDisplayed()
        composeRule.onNodeWithText("2 aggiornamenti", substring = true)
            .assertIsDisplayed()
        composeRule.onNodeWithText("Carica altri eventi").assertIsDisplayed()
    }

    @Test
    fun emptyFeedShowsDisabledPushRecoveryWithoutBreakingMonitoring() {
        val now = Clock.System.now()
        composeRule.setContent {
            AlembicMonitorTheme {
                EventsContent(
                    state = LoadState.Success(
                        EventsPage(1, now, emptyList(), null),
                        DataSource.NETWORK,
                        0
                    ),
                    selectedCategory = EventFilter.ALL,
                    selectedDays = 7,
                    refreshing = false,
                    loadingNext = false,
                    pushStatus = PushStatus.DISABLED,
                    onCategorySelected = {},
                    onDaysSelected = {},
                    onEventSelected = {},
                    onLoadNext = {},
                    onRetry = {}
                )
            }
        }

        composeRule.onNodeWithText("Nessun dato disponibile").assertIsDisplayed()
        composeRule.onNodeWithText("Notifiche disattivate").assertIsDisplayed()
        composeRule.onNodeWithText("Gestisci notifiche").assertIsDisplayed()
    }

    @Test
    fun feedErrorIsRetryable() {
        composeRule.setContent {
            AlembicMonitorTheme {
                EventsContent(
                    state = LoadState.Error("Server non disponibile", retryable = true),
                    selectedCategory = EventFilter.ALL,
                    selectedDays = 7,
                    refreshing = false,
                    loadingNext = false,
                    pushStatus = PushStatus.ERROR,
                    onCategorySelected = {},
                    onDaysSelected = {},
                    onEventSelected = {},
                    onLoadNext = {},
                    onRetry = {}
                )
            }
        }
        composeRule.onNodeWithText("Server non disponibile").assertIsDisplayed()
        composeRule.onNodeWithText("Riprova").assertIsDisplayed()
    }

    @Test
    fun allEventFiltersRemainVisibleAtTwoHundredPercentFontScale() {
        val now = Clock.System.now()
        composeRule.setContent {
            AlembicMonitorTheme {
                CompositionLocalProvider(LocalDensity provides Density(1f, 2f)) {
                    EventsContent(
                        state = LoadState.Success(
                            EventsPage(1, now, emptyList(), null),
                            DataSource.NETWORK,
                            0
                        ),
                        selectedCategory = EventFilter.ALL,
                        selectedDays = 30,
                        refreshing = false,
                        loadingNext = false,
                        pushStatus = PushStatus.ENABLED,
                        onCategorySelected = {},
                        onDaysSelected = {},
                        onEventSelected = {},
                        onLoadNext = {},
                        onRetry = {}
                    )
                }
            }
        }

        composeRule.onNodeWithText("Tutti").assertIsDisplayed()
        composeRule.onNodeWithText("Critici").assertIsDisplayed()
        composeRule.onNodeWithText("Trading").assertIsDisplayed()
        composeRule.onNodeWithText("Sistema").assertIsDisplayed()
        composeRule.onNodeWithText("30 giorni").assertIsDisplayed()
    }

    @Test
    fun missingDetailRendersSafeRetryableError() {
        composeRule.setContent {
            AlembicMonitorTheme {
                EventDetailContent(
                    state = LoadState.Error(
                        "Evento non disponibile",
                        retryable = true
                    ),
                    onRetry = {}
                )
            }
        }
        composeRule.onNodeWithText("Evento non disponibile").assertIsDisplayed()
        composeRule.onNodeWithText("Riprova").assertIsDisplayed()
    }
}
