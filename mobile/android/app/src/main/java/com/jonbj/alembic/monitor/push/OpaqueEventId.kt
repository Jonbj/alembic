package com.jonbj.alembic.monitor.push

@JvmInline
value class OpaqueEventId private constructor(val value: String) {
    companion object {
        private val VALID_VALUE = Regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

        fun parse(value: String?): OpaqueEventId? =
            value?.takeIf(VALID_VALUE::matches)?.let(::OpaqueEventId)
    }
}
