package com.jonbj.alembic.monitor.feature.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.rounded.Science
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.jonbj.alembic.monitor.R
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlembicTopBar(
    detail: Boolean,
    onBack: () -> Unit,
    onLogout: suspend () -> Unit
) {
    val scope = rememberCoroutineScope()
    CenterAlignedTopAppBar(
        title = {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Rounded.Science,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(22.dp)
                )
                Text(
                    text = stringResource(
                        if (detail) R.string.event_detail_title else R.string.app_name
                    ),
                    style = MaterialTheme.typography.titleMedium
                )
            }
        },
        navigationIcon = {
            if (detail) {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Rounded.ArrowBack,
                        contentDescription = stringResource(R.string.back)
                    )
                }
            }
        },
        actions = {
            if (!detail) {
                IconButton(onClick = { scope.launch { onLogout() } }) {
                    Icon(
                        Icons.AutoMirrored.Rounded.Logout,
                        contentDescription = stringResource(R.string.logout)
                    )
                }
            }
        }
    )
}
