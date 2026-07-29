package com.jonbj.alembic.monitor.push

import android.app.Application
import android.content.Intent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class DeepLinkCoordinatorTest {

    @Test
    fun `accepts only internal opaque event intents and consumes once`() {
        val coordinator = DeepLinkCoordinator()
        val eventId = "15af48e4-2be5-4ea0-969f-a59ca154bf79"
        val intent = Intent().apply {
            action = DeepLinkCoordinator.ACTION_OPEN_EVENT
            putExtra(DeepLinkCoordinator.EXTRA_EVENT_ID, eventId)
            putExtra("summary", "must be ignored")
        }

        assertTrue(coordinator.accept(intent))
        val opaqueEventId = requireNotNull(OpaqueEventId.parse(eventId))
        assertEquals(opaqueEventId, coordinator.pendingEventId.value)
        coordinator.consume(opaqueEventId)
        assertNull(coordinator.pendingEventId.value)
    }

    @Test
    fun `rejects external actions and malformed identifiers`() {
        val coordinator = DeepLinkCoordinator()
        assertFalse(
            coordinator.accept(
                Intent("https://example.invalid").putExtra(
                    DeepLinkCoordinator.EXTRA_EVENT_ID,
                    "../credentials"
                )
            )
        )
        assertNull(coordinator.pendingEventId.value)
    }
}
