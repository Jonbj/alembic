package com.jonbj.alembic.monitor.app.navigation

import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.NavType
import androidx.navigation.navArgument
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jonbj.alembic.monitor.app.di.AppContainer
import com.jonbj.alembic.monitor.app.viewModelFactory
import com.jonbj.alembic.monitor.feature.events.EventsScreen
import com.jonbj.alembic.monitor.feature.events.EventDetailScreen
import com.jonbj.alembic.monitor.feature.events.EventDetailViewModel
import com.jonbj.alembic.monitor.feature.login.AlembicTopBar
import com.jonbj.alembic.monitor.feature.performance.PerformanceScreen
import com.jonbj.alembic.monitor.feature.portfolio.PortfolioScreen
import com.jonbj.alembic.monitor.feature.push.PushPermissionPrompt
import com.jonbj.alembic.monitor.feature.status.StatusScreen
import com.jonbj.alembic.monitor.push.OpaqueEventId

@Composable
fun MainScaffold(container: AppContainer) {
    val navController = rememberNavController()
    val lifecycleOwner = LocalLifecycleOwner.current
    val refreshCoordinator = container.foregroundRefreshCoordinator
    val pushStatus by container.pushRegistrationRepository.status
        .collectAsStateWithLifecycle()
    val pendingEventId by container.deepLinkCoordinator.pendingEventId
        .collectAsStateWithLifecycle()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination
    val showingDetail = currentDestination?.route == Destination.EventDetail.route

    PushPermissionPrompt(container.pushCoordinator)

    LaunchedEffect(pendingEventId) {
        container.deepLinkCoordinator.authenticatedEventId()?.let { eventId ->
            navController.navigate(Destination.EventDetail.route(eventId)) {
                launchSingleTop = true
            }
            container.deepLinkCoordinator.consume(eventId)
        }
    }

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
            if (!showingDetail) {
                MonitorBottomBar(
                    currentRoute = currentDestination?.route,
                    onDestinationSelected = { destination ->
                        navController.navigate(destination.route) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                )
            }
        },
        topBar = {
            AlembicTopBar(
                detail = showingDetail,
                onBack = { navController.popBackStack() },
                onLogout = { container.logout() }
            )
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
                    }),
                    pushStatus = pushStatus,
                    onEventSelected = { rawEventId ->
                        OpaqueEventId.parse(rawEventId)?.let {
                            navController.navigate(Destination.EventDetail.route(it))
                        }
                    }
                )
            }
            composable(
                route = Destination.EventDetail.route,
                arguments = listOf(
                    navArgument("eventId") { type = NavType.StringType }
                )
            ) { entry ->
                val eventId = requireNotNull(
                    OpaqueEventId.parse(entry.arguments?.getString("eventId"))
                )
                EventDetailScreen(
                    viewModel(
                        key = eventId.value,
                        factory = viewModelFactory {
                            EventDetailViewModel(
                                eventId,
                                container.eventsRepository
                            )
                        }
                    )
                )
            }
        }
    }
}

@Composable
internal fun MonitorBottomBar(
    currentRoute: String?,
    onDestinationSelected: (Destination) -> Unit
) {
    val largeText = LocalDensity.current.fontScale >= 1.45f
    NavigationBar(
        modifier = Modifier.height(if (largeText) 96.dp else 80.dp),
        tonalElevation = 0.dp
    ) {
        bottomNavItems.forEach { item ->
            NavigationBarItem(
                icon = {
                    Icon(
                        item.icon,
                        contentDescription = stringResource(item.labelRes)
                    )
                },
                label = {
                    Text(
                        text = stringResource(item.labelRes),
                        style = if (largeText) {
                            MaterialTheme.typography.labelMedium.copy(
                                fontSize = 10.sp,
                                lineHeight = 12.sp
                            )
                        } else {
                            MaterialTheme.typography.labelMedium
                        },
                        maxLines = 2,
                        textAlign = TextAlign.Center
                    )
                },
                selected = currentRoute == item.destination.route,
                onClick = { onDestinationSelected(item.destination) }
            )
        }
    }
}
