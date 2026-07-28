package com.jonbj.alembic.monitor.feature.portfolio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.data.repository.PortfolioRepository
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class PortfolioViewModel(
    private val repository: PortfolioRepository
) : ViewModel() {

    val state = repository.positions
    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()
    private var activeRefreshes = 0

    init {
        refresh()
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            activeRefreshes += 1
            _isRefreshing.value = true
            try {
                repository.refresh(force)
            } finally {
                activeRefreshes -= 1
                _isRefreshing.value = activeRefreshes > 0
            }
        }
    }
}
