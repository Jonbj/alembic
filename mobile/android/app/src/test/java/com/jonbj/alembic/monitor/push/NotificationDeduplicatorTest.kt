package com.jonbj.alembic.monitor.push

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationDeduplicatorTest {

    @Test
    fun `same event transition is notified once`() {
        val storage = InMemoryDeliveryFingerprintStore()
        val deduplicator = NotificationDeduplicator(storage)
        val payload = PushPayload(
            eventId = "15af48e4-2be5-4ea0-969f-a59ca154bf79",
            transition = PushTransition.RECOVERED,
            severity = PushSeverity.INFO
        )

        assertTrue(deduplicator.shouldNotify(payload))
        assertFalse(deduplicator.shouldNotify(payload))
        assertTrue(
            deduplicator.shouldNotify(
                payload.copy(transition = PushTransition.OPENED)
            )
        )
    }
}
