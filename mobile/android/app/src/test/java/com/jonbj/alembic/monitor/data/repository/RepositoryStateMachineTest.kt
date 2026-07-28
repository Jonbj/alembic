package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.ContentMode
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.MobileError
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RepositoryStateMachineTest {

    @Test
    fun `old cached data is explicitly stale`() {
        val state = successFromCache("cached", STALE_AFTER_SECONDS + 1)

        assertEquals(ContentMode.STALE, state.mode)
    }

    @Test
    fun `mandatory update keeps cache separate from live interpretation`() {
        val state = failureState(
            MobileError.Version("update required"),
            cached = "cached",
            cachedAgeSeconds = 10
        )

        assertTrue(state is LoadState.Error)
        state as LoadState.Error
        assertEquals(ContentMode.INCOMPATIBLE, state.mode)
        assertEquals("cached", state.cached)
    }

    @Test
    fun `expired session returns unauthenticated without exposing cached data`() {
        val state = failureState(
            MobileError.Auth("expired", requireRelogin = true),
            cached = "cached",
            cachedAgeSeconds = 10
        )

        assertTrue(state is LoadState.Error)
        state as LoadState.Error
        assertEquals(ContentMode.UNAUTHENTICATED, state.mode)
        assertNull(state.cached)
    }
}
