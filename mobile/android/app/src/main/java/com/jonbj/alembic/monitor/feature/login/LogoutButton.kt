package com.jonbj.alembic.monitor.feature.login

import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.res.stringResource
import com.jonbj.alembic.monitor.R
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogoutTopBarButton(onLogout: suspend () -> Unit) {
    val scope = rememberCoroutineScope()
    TopAppBar(
        title = { Text(stringResource(R.string.app_name)) },
        actions = {
            Button(onClick = {
                scope.launch {
                    onLogout()
                }
            }) {
                Text(stringResource(R.string.logout))
            }
        }
    )
}
