package com.jonbj.alembic.monitor.app.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.EventNote
import androidx.compose.material.icons.filled.Wallet
import androidx.compose.ui.graphics.vector.ImageVector
import com.jonbj.alembic.monitor.R

sealed class Destination(val route: String) {
    data object Login : Destination("login")
    data object Status : Destination("status")
    data object Performance : Destination("performance")
    data object Portfolio : Destination("portfolio")
    data object Events : Destination("events")
}

data class BottomNavItem(
    val destination: Destination,
    val labelRes: Int,
    val icon: ImageVector
)

val bottomNavItems = listOf(
    BottomNavItem(Destination.Status, R.string.nav_status, Icons.Default.Dashboard),
    BottomNavItem(Destination.Performance, R.string.nav_performance, Icons.Default.Analytics),
    BottomNavItem(Destination.Portfolio, R.string.nav_portfolio, Icons.Default.Wallet),
    BottomNavItem(Destination.Events, R.string.nav_events, Icons.Default.EventNote)
)
