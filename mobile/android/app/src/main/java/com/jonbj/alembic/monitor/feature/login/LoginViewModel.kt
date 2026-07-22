package com.jonbj.alembic.monitor.feature.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.app.di.AppModule
import com.jonbj.alembic.monitor.data.repository.AuthRepository
import com.jonbj.alembic.monitor.data.repository.DeviceInfoProvider
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class LoginUiState {
    data object Idle : LoginUiState()
    data object Loading : LoginUiState()
    data object LoggedIn : LoginUiState()
    data class Error(val message: String) : LoginUiState()
}

class LoginViewModel(
    private val authRepository: AuthRepository = AppModule.authRepository,
    private val deviceInfoProvider: DeviceInfoProvider = AppModule.deviceInfoProvider
) : ViewModel() {

    private val _state = MutableStateFlow<LoginUiState>(LoginUiState.Idle)
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun login(username: String, password: String) {
        if (username.isBlank() || password.isBlank()) {
            _state.value = LoginUiState.Error("Username e password sono obbligatori")
            return
        }
        _state.value = LoginUiState.Loading
        viewModelScope.launch {
            val result = authRepository.login(
                username = username,
                password = password,
                installationId = deviceInfoProvider.installationId(),
                deviceName = deviceInfoProvider.deviceName()
            )
            _state.value = if (result.isSuccess) {
                LoginUiState.LoggedIn
            } else {
                val error = result.exceptionOrNull()
                LoginUiState.Error(error?.message ?: "Accesso fallito")
            }
        }
    }
}
