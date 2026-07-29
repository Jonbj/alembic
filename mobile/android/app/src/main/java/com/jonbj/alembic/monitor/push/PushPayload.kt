package com.jonbj.alembic.monitor.push

enum class PushTransition {
    OPENED,
    ESCALATED,
    RECOVERED,
    TERMINAL,
    CLOSED
}

enum class PushSeverity {
    CRITICAL,
    WARNING,
    INFO
}

data class PushPayload(
    val eventId: OpaqueEventId,
    val transition: PushTransition,
    val severity: PushSeverity
) {
    val fingerprint: String get() = "${eventId.value}:${transition.name}"

    companion object {
        fun parse(data: Map<String, String>): PushPayload? {
            if (data["contract_version"] != "1") return null
            val eventId = OpaqueEventId.parse(data["event_id"])
                ?: return null
            val transition = when (data["transition"]?.lowercase()) {
                "open", "opened" -> PushTransition.OPENED
                "escalate", "escalated" -> PushTransition.ESCALATED
                "recover", "recovered" -> PushTransition.RECOVERED
                "terminal" -> PushTransition.TERMINAL
                "close", "closed" -> PushTransition.CLOSED
                else -> return null
            }
            val severity = when (data["severity"]?.lowercase()) {
                "critical" -> PushSeverity.CRITICAL
                "warning" -> PushSeverity.WARNING
                "info" -> PushSeverity.INFO
                else -> return null
            }
            return PushPayload(eventId, transition, severity)
        }
    }
}
