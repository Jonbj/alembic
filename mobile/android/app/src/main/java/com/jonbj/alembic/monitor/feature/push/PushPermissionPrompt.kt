package com.jonbj.alembic.monitor.feature.push

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.push.PushCoordinator
import kotlinx.coroutines.launch

@Composable
fun PushPermissionPrompt(coordinator: PushCoordinator) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    var showExplanation by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        scope.launch {
            coordinator.onPermissionResult(granted)
        }
    }

    DisposableEffect(lifecycleOwner, coordinator) {
        fun evaluatePermission() {
            scope.launch {
                val granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                    ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.POST_NOTIFICATIONS
                    ) == PackageManager.PERMISSION_GRANTED
                when {
                    granted -> coordinator.onPermissionResult(true)
                    coordinator.shouldExplainPermission -> {
                        showExplanation = true
                    }
                    else -> coordinator.onPermissionResult(false)
                }
            }
        }
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) evaluatePermission()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            evaluatePermission()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    if (showExplanation) {
        AlertDialog(
            onDismissRequest = {
                showExplanation = false
                scope.launch {
                    coordinator.onPermissionDeferred()
                }
            },
            title = { Text(stringResource(R.string.push_permission_title)) },
            text = {
                Text(stringResource(R.string.push_permission_explanation))
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showExplanation = false
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            scope.launch {
                                coordinator.onPermissionResult(true)
                            }
                        }
                    }
                ) {
                    Text(stringResource(R.string.push_permission_allow))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showExplanation = false
                        scope.launch {
                            coordinator.onPermissionDeferred()
                        }
                    }
                ) {
                    Text(stringResource(R.string.push_permission_not_now))
                }
            }
        )
    }
}
