package com.jonbj.alembic.monitor.app.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalanceWallet
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material.icons.automirrored.rounded.ShowChart
import androidx.compose.material.icons.rounded.SpaceDashboard
import androidx.compose.ui.graphics.vector.ImageVector
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.push.OpaqueEventId

sealed class Destination(val route: String) {
    data object Login : Destination("login")
    data object Status : Destination("status")
    data object Performance : Destination("performance")
    data object Portfolio : Destination("portfolio")
    data object Events : Destination("events")
    data object EventDetail : Destination("events/{eventId}") {
        fun route(eventId: OpaqueEventId) =
            "events/${android.net.Uri.encode(eventId.value)}"
    }
}

data class BottomNavItem(
    val destination: Destination,
    val labelRes: Int,
    val icon: ImageVector
)

val bottomNavItems = listOf(
    BottomNavItem(Destination.Status, R.string.nav_status, Icons.Rounded.SpaceDashboard),
    BottomNavItem(Destination.Performance, R.string.nav_performance, Icons.AutoMirrored.Rounded.ShowChart),
    BottomNavItem(Destination.Portfolio, R.string.nav_portfolio, Icons.Rounded.AccountBalanceWallet),
    BottomNavItem(Destination.Events, R.string.nav_events, Icons.Rounded.Notifications)
)
