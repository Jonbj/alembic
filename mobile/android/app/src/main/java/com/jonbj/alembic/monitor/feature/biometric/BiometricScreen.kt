package com.jonbj.alembic.monitor.feature.biometric

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Fingerprint
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.core.security.BiometricGate
import com.jonbj.alembic.monitor.core.security.BiometricResult
import com.jonbj.alembic.monitor.ui.components.MonitorCard
import kotlinx.coroutines.launch

@Composable
fun BiometricLockScreen(
    biometricGate: BiometricGate,
    activity: FragmentActivity,
    onUnlocked: () -> Unit,
    onLogout: suspend () -> Unit
) {
    val scope = rememberCoroutineScope()
    Column(
        modifier = Modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        MonitorCard(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Icon(
                    Icons.Rounded.Fingerprint,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary
                )
                Text(
                    text = stringResource(R.string.biometric_title),
                    style = MaterialTheme.typography.headlineMedium,
                    textAlign = TextAlign.Center
                )
                Text(
                    text = stringResource(R.string.biometric_subtitle),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center
                )
                Button(
                    onClick = {
                        biometricGate.authenticate(
                            activity = activity,
                            title = activity.getString(R.string.biometric_title),
                            subtitle = activity.getString(R.string.biometric_subtitle)
                        ) { result ->
                            if (result is BiometricResult.Success) onUnlocked()
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(stringResource(R.string.unlock))
                }
                TextButton(onClick = { scope.launch { onLogout() } }) {
                    Text(stringResource(R.string.logout))
                }
            }
        }
    }
}
