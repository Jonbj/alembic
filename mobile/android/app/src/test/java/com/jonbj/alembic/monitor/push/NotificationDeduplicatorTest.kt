package com.jonbj.alembic.monitor.push

import android.app.Application
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class NotificationDeduplicatorTest {

    @Test
    fun `same event transition is notified once`() {
        val storage = InMemoryDeliveryFingerprintStore()
        val deduplicator = NotificationDeduplicator(storage)
        val payload = PushPayload(
            eventId = requireNotNull(
                OpaqueEventId.parse("15af48e4-2be5-4ea0-969f-a59ca154bf79")
            ),
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

    @Test
    fun `a delivered transition remains deduplicated after many later events`() {
        val context = RuntimeEnvironment.getApplication()
        context.getSharedPreferences(
            "alembic_push_delivery",
            Application.MODE_PRIVATE
        ).edit().clear().commit()
        val deduplicator = NotificationDeduplicator(
            SharedPreferencesDeliveryFingerprintStore(context)
        )
        val original = PushPayload(
            eventId = requireNotNull(OpaqueEventId.parse("original-event")),
            transition = PushTransition.OPENED,
            severity = PushSeverity.CRITICAL
        )
        assertTrue(deduplicator.shouldNotify(original))
        repeat(256) { index ->
            assertTrue(
                deduplicator.shouldNotify(
                    original.copy(
                        eventId = requireNotNull(
                            OpaqueEventId.parse("later-event-$index")
                        )
                    )
                )
            )
        }

        assertFalse(deduplicator.shouldNotify(original))
    }
}
