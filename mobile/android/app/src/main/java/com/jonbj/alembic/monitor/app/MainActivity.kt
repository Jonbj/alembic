package com.jonbj.alembic.monitor.app

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.viewmodel.compose.viewModel
import com.jonbj.alembic.monitor.MonitorApplication
import com.jonbj.alembic.monitor.app.navigation.MainScaffold
import com.jonbj.alembic.monitor.feature.biometric.BiometricLockScreen
import com.jonbj.alembic.monitor.feature.login.LoginScreen
import com.jonbj.alembic.monitor.feature.login.LoginViewModel
import com.jonbj.alembic.monitor.ui.theme.AlembicMonitorTheme

class MainActivity : FragmentActivity() {

    private val container by lazy { (application as MonitorApplication).container }
    private val sessionVault by lazy { container.sessionVault }
    private val appLock by lazy { container.appLock }
    private val biometricGate by lazy { container.biometricGate }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        acceptNotificationIntent(intent)

        setContent {
            AlembicMonitorTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val session by sessionVault.sessionFlow.collectAsStateWithLifecycle()
                    val isLocked by appLock.isLocked.collectAsStateWithLifecycle()

                    when {
                        session == null -> LoginScreen(
                            viewModel(
                                factory = viewModelFactory {
                                    LoginViewModel(
                                        authRepository = container.authRepository,
                                        deviceInfoProvider = container.deviceInfoProvider,
                                        defaultServerUrl = com.jonbj.alembic.monitor.BuildConfig.BASE_URL
                                    )
                                }
                            )
                        )
                        isLocked -> BiometricLockScreen(
                            biometricGate = biometricGate,
                            activity = this,
                            onUnlocked = { appLock.unlock() },
                            onLogout = {
                                container.logout()
                            }
                        )
                        else -> MainScaffold(container)
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        acceptNotificationIntent(intent)
    }

    private fun acceptNotificationIntent(intent: Intent?) {
        container.deepLinkCoordinator.accept(intent)
    }

    override fun onResume() {
        super.onResume()
        appLock.onAppForeground()
    }

    override fun onPause() {
        super.onPause()
        appLock.onAppBackground()
    }
}
