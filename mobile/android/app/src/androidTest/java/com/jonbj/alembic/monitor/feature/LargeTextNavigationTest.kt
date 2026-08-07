package com.jonbj.alembic.monitor.feature

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.Density
import com.jonbj.alembic.monitor.app.navigation.Destination
import com.jonbj.alembic.monitor.app.navigation.MonitorBottomBar
import com.jonbj.alembic.monitor.feature.performance.PerformancePeriod
import com.jonbj.alembic.monitor.feature.performance.PeriodSelector
import com.jonbj.alembic.monitor.ui.theme.AlembicMonitorTheme
import org.junit.Rule
import org.junit.Test

class LargeTextNavigationTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun canonicalNavigationLabelsRemainVisibleAtOneHundredFiftyPercent() {
        composeRule.setContent {
            AlembicMonitorTheme {
                CompositionLocalProvider(LocalDensity provides Density(1f, 1.5f)) {
                    MonitorBottomBar(
                        currentRoute = Destination.Status.route,
                        onDestinationSelected = {}
                    )
                }
            }
        }

        listOf("Stato", "Andamento", "Portafoglio", "Eventi").forEach { label ->
            composeRule.onNodeWithText(label).assertIsDisplayed()
        }
    }

    @Test
    fun everyPerformancePeriodRemainsVisibleAtTwoHundredPercent() {
        composeRule.setContent {
            AlembicMonitorTheme {
                CompositionLocalProvider(LocalDensity provides Density(1f, 2f)) {
                    PeriodSelector(
                        selected = PerformancePeriod.ONE_MONTH,
                        onSelected = {}
                    )
                }
            }
        }

        listOf("1S", "1M", "3M", "6M", "1A", "Tutto").forEach { label ->
            composeRule.onNodeWithText(label).assertIsDisplayed()
        }
    }
}
