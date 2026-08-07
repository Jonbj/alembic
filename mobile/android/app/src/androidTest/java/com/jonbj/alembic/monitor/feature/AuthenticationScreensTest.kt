package com.jonbj.alembic.monitor.feature

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import com.jonbj.alembic.monitor.feature.biometric.BiometricLockContent
import com.jonbj.alembic.monitor.feature.login.LoginContent
import com.jonbj.alembic.monitor.feature.login.LoginUiState
import com.jonbj.alembic.monitor.ui.theme.AlembicMonitorTheme
import org.junit.Rule
import org.junit.Test

class AuthenticationScreensTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun loginControlsRemainReachableAtTwoHundredPercentFontScale() {
        composeRule.setContent {
            AlembicMonitorTheme {
                CompositionLocalProvider(LocalDensity provides Density(1f, 2f)) {
                    LoginContent(
                        state = LoginUiState.Idle,
                        defaultServerUrl = "https://alembic.lan",
                        defaultDeviceName = "Pixel 9",
                        onLogin = { _, _, _, _ -> }
                    )
                }
            }
        }

        composeRule.onNodeWithText("Il tuo monitor Alembic").assertIsDisplayed()
        composeRule.onNodeWithText("Indirizzo del server").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("Password").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("Accedi").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun biometricControlsRemainReachableAtTwoHundredPercentFontScale() {
        composeRule.setContent {
            AlembicMonitorTheme {
                CompositionLocalProvider(LocalDensity provides Density(1f, 2f)) {
                    BiometricLockContent(onUnlock = {}, onLogout = {})
                }
            }
        }

        composeRule.onNodeWithText("Sblocca Alembic Monitor").assertIsDisplayed()
        composeRule.onNodeWithText("Sblocca").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("Esci").performScrollTo().assertIsDisplayed()
    }
}
