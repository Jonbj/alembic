package com.jonbj.alembic.monitor.core.network

import com.jonbj.alembic.monitor.core.network.dto.DeviceRegistrationResponse
import com.jonbj.alembic.monitor.core.network.dto.PerformanceResponse
import com.jonbj.alembic.monitor.core.network.dto.PositionsResponse
import com.jonbj.alembic.monitor.core.network.dto.SnapshotResponse
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MobileDtoContractTest {

    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun `snapshot decodes named pipeline components and structured degradations`() {
        val payload = """
            {
              "contract_version": 1,
              "as_of": "2026-07-28T10:00:00Z",
              "data_age_seconds": 10,
              "currency": "USD",
              "min_supported_app_version": "1.0.0",
              "latest_app_version": "1.0.0",
              "operational": {
                "state": "degraded",
                "primary_reason": "Redis in sola lettura",
                "mode": "paper",
                "market_phase": "open",
                "pipeline_expected": true,
                "active_incident_count": 1
              },
              "portfolio": {
                "nav": null,
                "open_positions": null,
                "source": null
              },
              "pipeline": {
                "database": {"status": "fresh", "age_seconds": 0},
                "redis": {"status": "aging", "age_seconds": 12, "writeable": false}
              },
              "strategies": [],
              "degradations": [
                {"component": "redis", "reason": "read_only", "severity": "warning"}
              ]
            }
        """.trimIndent()

        val decoded = json.decodeFromString(SnapshotResponse.serializer(), payload)

        assertEquals(setOf("database", "redis"), decoded.pipeline.keys)
        assertEquals(false, decoded.pipeline.getValue("redis").writeable)
        assertEquals("read_only", decoded.degradations.single().reason)
        assertNull(decoded.portfolio.openPositions)
        assertNull(decoded.portfolio.source)
    }

    @Test
    fun `nullable broker values decode without zero substitution`() {
        val common = """
            "contract_version": 1,
            "as_of": "2026-07-28T10:00:00Z",
            "data_age_seconds": 30,
            "currency": "USD",
            "min_supported_app_version": "1.0.0",
            "latest_app_version": "1.0.0"
        """.trimIndent()

        val performance = json.decodeFromString(
            PerformanceResponse.serializer(),
            """{$common,
              "period":"1m",
              "period_start":"2026-06-28T00:00:00Z",
              "period_end":"2026-07-28T10:00:00Z",
              "summary":{
                "nav_start":null,"nav_end":null,"nav_change":null,
                "portfolio_return":null,"max_drawdown":null
              },
              "points":[],"degradations":[]
            }"""
        )
        val positions = json.decodeFromString(
            PositionsResponse.serializer(),
            """{$common,
              "summary":{"count":1,"market_value":null,"unrealized_pnl":null},
              "items":[{
                "symbol":"MSFT","qty":1.0,"avg_entry_price":null,
                "current_price":null,"market_value":null,"position_weight":null,
                "unrealized_pnl":null,"unrealized_return":null,"entry_time":null
              }],
              "degradations":[]
            }"""
        )

        assertNull(performance.summary.navStart)
        assertNull(performance.summary.maxDrawdown)
        assertNull(positions.summary.marketValue)
        assertNull(positions.items.single().entryTime)
    }

    @Test
    fun `device registration decodes the server response envelope`() {
        val decoded = json.decodeFromString(
            DeviceRegistrationResponse.serializer(),
            """
              {"device":{
                "id":"4e2f8073-cf0e-4e26-9b3e-b358c5ad1d7e",
                "installation_id":"installation-1",
                "firebase_installation_id":null,
                "name":"Pixel 9",
                "app_version":"1.0.0",
                "push_enabled":false
              }}
            """.trimIndent()
        )

        assertEquals("4e2f8073-cf0e-4e26-9b3e-b358c5ad1d7e", decoded.device.id)
        assertEquals(false, decoded.device.pushEnabled)
    }
}
