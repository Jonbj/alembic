package com.jonbj.alembic.monitor.feature

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import com.jonbj.alembic.monitor.core.model.ContentMode
import com.jonbj.alembic.monitor.core.model.DataSource
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.MarketPhase
import com.jonbj.alembic.monitor.core.model.Mode
import com.jonbj.alembic.monitor.core.model.Operational
import com.jonbj.alembic.monitor.core.model.OperationalState
import com.jonbj.alembic.monitor.core.model.Performance
import com.jonbj.alembic.monitor.core.model.PerformancePoint
import com.jonbj.alembic.monitor.core.model.PerformanceSummary
import com.jonbj.alembic.monitor.core.model.Portfolio
import com.jonbj.alembic.monitor.core.model.PositionSummary
import com.jonbj.alembic.monitor.core.model.Positions
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.feature.performance.PerformanceContent
import com.jonbj.alembic.monitor.feature.performance.PerformancePeriod
import com.jonbj.alembic.monitor.feature.portfolio.PortfolioContent
import com.jonbj.alembic.monitor.feature.status.StatusContent
import com.jonbj.alembic.monitor.ui.theme.AlembicMonitorTheme
import kotlinx.datetime.Clock
import org.junit.Rule
import org.junit.Test

class MonitoringScreensTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun statusRendersOperationalStateWithTalkBackSemantics() {
        renderStatus(OperationalState.OPERATIONAL)

        composeRule.onNodeWithText("OPERATIVO").assertIsDisplayed()
        composeRule.onNodeWithContentDescription("OPERATIVO", substring = true)
            .assertIsDisplayed()
        composeRule.onNodeWithText("PAPER").assertIsDisplayed()
    }

    @Test
    fun statusRendersDegradedBlockedAndPausedWithoutColorOnlyMeaning() {
        val labels = listOf(
            OperationalState.DEGRADED to "DEGRADATO",
            OperationalState.BLOCKED to "BLOCCATO",
            OperationalState.PAUSED to "IN PAUSA"
        )
        var selected by mutableStateOf(labels.first().first)
        composeRule.setContent {
            AlembicMonitorTheme {
                StatusContent(
                    state = success(snapshot(selected)),
                    refreshing = false,
                    onRefresh = {}
                )
            }
        }
        labels.forEach { (state, label) ->
            composeRule.runOnIdle { selected = state }
            composeRule.onNodeWithText(label).assertIsDisplayed()
        }
    }

    @Test
    fun offlineStateAlwaysShowsAgeAtTwoHundredPercentFontScale() {
        composeRule.setContent {
            AlembicMonitorTheme(darkTheme = false) {
                CompositionLocalProvider(LocalDensity provides Density(1f, 2f)) {
                    StatusContent(
                        state = LoadState.Success(
                            data = snapshot(OperationalState.OPERATIONAL),
                            source = DataSource.CACHE,
                            dataAgeSeconds = 480,
                            mode = ContentMode.OFFLINE
                        ),
                        refreshing = false,
                        onRefresh = {}
                    )
                }
            }
        }

        composeRule.onNodeWithText("OFFLINE", substring = true).assertIsDisplayed()
        composeRule.onNodeWithText("8 minuti", substring = true).assertIsDisplayed()
    }

    @Test
    fun mandatoryUpdateIsExplicitAndNotRetryable() {
        composeRule.setContent {
            AlembicMonitorTheme {
                StatusContent(
                    state = LoadState.Error(
                        message = "Aggiornamento obbligatorio",
                        retryable = false,
                        mode = ContentMode.INCOMPATIBLE
                    ),
                    refreshing = false,
                    onRefresh = {}
                )
            }
        }

        composeRule.onNodeWithText("Aggiornamento obbligatorio").assertIsDisplayed()
        composeRule.onAllNodesWithText("Riprova").assertCountEquals(0)
    }

    @Test
    fun performanceHasApprovedPeriodsChartSummaryAndNoInventedBenchmark() {
        val now = Clock.System.now()
        val performance = Performance(
            contractVersion = 1,
            asOf = now,
            dataAgeSeconds = 10,
            currency = "USD",
            period = "1m",
            periodStart = now,
            periodEnd = now,
            summary = PerformanceSummary(
                navStart = 100.0,
                navEnd = 101.0,
                navChange = 1.0,
                portfolioReturn = 0.01,
                realizedPnl = 0.5,
                maxDrawdown = 0.02,
                avgGrossExposure = 0.3,
                spyReturn = null,
                benchmarkReturn = null,
                alpha = null
            ),
            points = listOf(
                PerformancePoint(now, 100.0, 0.0, null),
                PerformancePoint(now, 101.0, -0.02, null)
            ),
            degradations = emptyList()
        )
        composeRule.setContent {
            AlembicMonitorTheme(darkTheme = true) {
                PerformanceContent(
                    state = LoadState.Success(performance, DataSource.NETWORK, 10),
                    selectedPeriod = PerformancePeriod.ONE_MONTH,
                    refreshing = false,
                    onPeriodSelected = {},
                    onRefresh = {}
                )
            }
        }

        composeRule.onNodeWithText("1S").assertIsDisplayed()
        composeRule.onNodeWithContentDescription("Grafico NAV", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("Mostra tabella accessibile")
            .performScrollTo()
            .assertIsDisplayed()
    }

    @Test
    fun emptyPortfolioStateIsExplicit() {
        val positions = Positions(
            contractVersion = 1,
            asOf = Clock.System.now(),
            dataAgeSeconds = 5,
            currency = "USD",
            summary = PositionSummary(0, 0.0, 0.0, 0.0),
            items = emptyList(),
            degradations = emptyList()
        )
        composeRule.setContent {
            AlembicMonitorTheme {
                PortfolioContent(
                    state = LoadState.Success(positions, DataSource.NETWORK, 5),
                    refreshing = false,
                    onRefresh = {}
                )
            }
        }

        composeRule.onNodeWithText("Nessun dato disponibile").assertIsDisplayed()
    }

    private fun renderStatus(state: OperationalState) {
        composeRule.setContent {
            AlembicMonitorTheme {
                StatusContent(success(snapshot(state)), refreshing = false, onRefresh = {})
            }
        }
    }

    private fun success(snapshot: Snapshot) =
        LoadState.Success(snapshot, DataSource.NETWORK, snapshot.dataAgeSeconds)

    private fun snapshot(state: OperationalState): Snapshot {
        val now = Clock.System.now()
        return Snapshot(
            contractVersion = 1,
            asOf = now,
            dataAgeSeconds = 10,
            currency = "USD",
            minSupportedAppVersion = "1.0.0",
            latestAppVersion = "1.0.0",
            operational = Operational(
                state = state,
                primaryReason = if (state == OperationalState.OPERATIONAL) null else "Motivo test",
                mode = Mode.PAPER,
                marketPhase = MarketPhase.OPEN,
                pipelineExpected = true,
                nextExpectedActivityAt = null,
                activeIncidentCount = 0
            ),
            portfolio = Portfolio(
                nav = 100_000.0,
                navChangeToday = 100.0,
                navReturnToday = 0.001,
                realizedPnlToday = 0.0,
                unrealizedPnl = -10.0,
                cash = 50_000.0,
                cashPct = 0.5,
                grossExposure = 0.5,
                grossExposureLimit = 0.6,
                currentDrawdown = 0.01,
                drawdownLimit = 0.05,
                openPositions = 2,
                source = "test"
            ),
            pipeline = emptyList(),
            strategies = emptyList(),
            degradations = emptyList()
        )
    }
}
