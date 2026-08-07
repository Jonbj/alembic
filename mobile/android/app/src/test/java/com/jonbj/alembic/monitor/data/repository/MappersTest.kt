package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.Mode
import org.junit.Assert.assertEquals
import org.junit.Test

class MappersTest {

    @Test
    fun strategyModesBecomeTypedAtTheDtoBoundary() {
        assertEquals(Mode.PAPER, parseMode("paper"))
        assertEquals(Mode.LIVE, parseMode("LIVE"))
        assertEquals(Mode.UNKNOWN, parseMode("unexpected"))
    }
}
