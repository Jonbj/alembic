package com.jonbj.alembic.monitor.ui.components

import com.jonbj.alembic.monitor.core.model.MarketPhase
import com.jonbj.alembic.monitor.core.model.Mode
import com.jonbj.alembic.monitor.core.model.Operational
import com.jonbj.alembic.monitor.core.model.OperationalState
import com.jonbj.alembic.monitor.core.model.Position
import org.junit.Assert.assertEquals
import org.junit.Test

class MonitoringPresentationTest {

    @Test
    fun unknownModeAlwaysRendersBlocked() {
        val operational = Operational(
            state = OperationalState.OPERATIONAL,
            primaryReason = null,
            mode = Mode.UNKNOWN,
            marketPhase = MarketPhase.OPEN,
            pipelineExpected = true,
            nextExpectedActivityAt = null,
            activeIncidentCount = 0
        )

        assertEquals(OperationalState.BLOCKED, effectiveOperationalState(operational))
    }

    @Test
    fun refreshCadenceFollowsServerExpectedWindow() {
        assertEquals(60_000L, foregroundRefreshIntervalMillis(pipelineExpected = true))
        assertEquals(300_000L, foregroundRefreshIntervalMillis(pipelineExpected = false))
    }

    @Test
    fun positionsAreSortedByWorstReturnThenLargestAbsoluteValue() {
        val positions = listOf(
            position("BEST", 0.15, 10_000.0),
            position("LOSS_SMALL", -0.10, 500.0),
            position("LOSS_LARGE", -0.10, -2_000.0),
            position("UNKNOWN", null, 50_000.0)
        )

        assertEquals(
            listOf("LOSS_LARGE", "LOSS_SMALL", "BEST", "UNKNOWN"),
            sortPositionsForRisk(positions).map { it.symbol }
        )
    }

    @Test
    fun monitoringValuesHandleSignsZeroAndNullWithoutInventingData() {
        assertEquals("+$12.50", formatSignedMoney(12.5, "USD"))
        assertEquals("-$12.50", formatSignedMoney(-12.5, "USD"))
        assertEquals("$0.00", formatSignedMoney(0.0, "USD"))
        assertEquals("Non disponibile", formatSignedMoney(null, "USD"))
        assertEquals("-12.50%", formatPercent(-0.125))
        assertEquals("0.00%", formatPercent(0.0))
        assertEquals("Non disponibile", formatPercent(null))
        assertEquals("0.125", formatQuantity(0.125))
        assertEquals("2", formatQuantity(2.0))
        assertEquals("Non disponibile", formatQuantity(null))
    }

    @Test
    fun ageFormattingIsCompactAndAccessible() {
        assertEquals("32 secondi", formatDataAge(32))
        assertEquals("8 minuti", formatDataAge(8 * 60))
        assertEquals("2 ore", formatDataAge(2 * 60 * 60))
        assertEquals("Non disponibile", formatDataAge(null))
    }

    private fun position(symbol: String, returnValue: Double?, marketValue: Double) = Position(
        symbol = symbol,
        qty = 1.0,
        avgEntryPrice = 1.0,
        currentPrice = 1.0,
        marketValue = marketValue,
        positionWeight = 0.1,
        unrealizedPnl = 0.0,
        unrealizedReturn = returnValue,
        entryTime = null
    )
}
