package com.jonbj.alembic.monitor.app.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.jonbj.alembic.monitor.app.di.AppContainer
import com.jonbj.alembic.monitor.app.viewModelFactory
import com.jonbj.alembic.monitor.feature.events.EventsScreen
import com.jonbj.alembic.monitor.feature.login.LogoutTopBarButton
import com.jonbj.alembic.monitor.feature.performance.PerformanceScreen
import com.jonbj.alembic.monitor.feature.portfolio.PortfolioScreen
import com.jonbj.alembic.monitor.feature.status.StatusScreen

@Composable
fun MainScaffold(container: AppContainer) {
    val navController = rememberNavController()
    val lifecycleOwner = LocalLifecycleOwner.current
    val refreshCoordinator = container.foregroundRefreshCoordinator

    DisposableEffect(lifecycleOwner, refreshCoordinator) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> refreshCoordinator.start()
                Lifecycle.Event.ON_STOP -> refreshCoordinator.stop()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            refreshCoordinator.start()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            refreshCoordinator.stop()
        }
    }

    Scaffold(
        bottomBar = {
            NavigationBar {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentDestination = navBackStackEntry?.destination
                bottomNavItems.forEach { item ->
                    NavigationBarItem(
                        icon = { Icon(item.icon, contentDescription = null) },
                        label = { Text(stringResource(item.labelRes)) },
                        selected = currentDestination?.hierarchy?.any { it.route == item.destination.route } == true,
                        onClick = {
                            navController.navigate(item.destination.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    )
                }
            }
        },
        topBar = {
            LogoutTopBarButton { container.authRepository.logout() }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Destination.Status.route,
            modifier = Modifier.padding(innerPadding)
        ) {
            composable(Destination.Status.route) {
                StatusScreen(
                    viewModel(factory = viewModelFactory {
                        com.jonbj.alembic.monitor.feature.status.StatusViewModel(
                            container.statusRepository
                        )
                    })
                )
            }
            composable(Destination.Performance.route) {
                PerformanceScreen(
                    viewModel(factory = viewModelFactory {
                        com.jonbj.alembic.monitor.feature.performance.PerformanceViewModel(
                            container.performanceRepository
                        )
                    })
                )
            }
            composable(Destination.Portfolio.route) {
                PortfolioScreen(
                    viewModel(factory = viewModelFactory {
                        com.jonbj.alembic.monitor.feature.portfolio.PortfolioViewModel(
                            container.portfolioRepository
                        )
                    })
                )
            }
            composable(Destination.Events.route) {
                EventsScreen(
                    viewModel(factory = viewModelFactory {
                        com.jonbj.alembic.monitor.feature.events.EventsViewModel(
                            container.eventsRepository
                        )
                    })
                )
            }
        }
    }
}
