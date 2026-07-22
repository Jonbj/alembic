package com.jonbj.alembic.monitor.app

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jonbj.alembic.monitor.app.di.AppModule
import com.jonbj.alembic.monitor.app.navigation.MainScaffold
import com.jonbj.alembic.monitor.feature.biometric.BiometricLockScreen
import com.jonbj.alembic.monitor.feature.login.LoginScreen
import com.jonbj.alembic.monitor.ui.theme.AlembicMonitorTheme

class MainActivity : ComponentActivity() {

    private val sessionVault = AppModule.sessionVault
    private val appLock = AppModule.appLock
    private val biometricGate = AppModule.biometricGate

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)

        setContent {
            AlembicMonitorTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val session by sessionVault.sessionFlow.collectAsStateWithLifecycle()
                    val isLocked by appLock.isLocked.collectAsStateWithLifecycle()

                    when {
                        session == null -> LoginScreen()
                        isLocked -> BiometricLockScreen(
                            biometricGate = biometricGate,
                            activity = this,
                            onUnlocked = { appLock.unlock() },
                            onLogout = {
                                AppModule.authRepository.logout()
                                sessionVault.clear()
                            }
                        )
                        else -> MainScaffold()
                    }
                }
            }
        }
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
