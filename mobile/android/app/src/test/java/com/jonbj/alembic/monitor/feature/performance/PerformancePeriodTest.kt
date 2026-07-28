package com.jonbj.alembic.monitor.feature.performance

import org.junit.Assert.assertEquals
import org.junit.Test

class PerformancePeriodTest {

    @Test
    fun periodsMatchTheApprovedApiOrderAndDefault() {
        assertEquals(
            listOf("1w", "1m", "3m", "6m", "1y", "all"),
            PerformancePeriod.entries.map { it.apiValue }
        )
        assertEquals(PerformancePeriod.ONE_MONTH, PerformancePeriod.DEFAULT)
    }
}
