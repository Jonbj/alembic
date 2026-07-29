package com.jonbj.alembic.monitor.push

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PushPayloadTest {

    @Test
    fun `accepts only versioned opaque routing data`() {
        val payload = PushPayload.parse(
            mapOf(
                "event_id" to "15af48e4-2be5-4ea0-969f-a59ca154bf79",
                "transition" to "opened",
                "severity" to "critical",
                "contract_version" to "1",
                "portfolio_value" to "100000"
            )
        )

        assertEquals("15af48e4-2be5-4ea0-969f-a59ca154bf79", payload?.eventId)
        assertEquals(PushTransition.OPENED, payload?.transition)
    }

    @Test
    fun `rejects malformed identifiers and unsupported transitions`() {
        assertNull(
            PushPayload.parse(
                mapOf(
                    "event_id" to "../secret",
                    "transition" to "trade",
                    "severity" to "critical",
                    "contract_version" to "1"
                )
            )
        )
    }
}
