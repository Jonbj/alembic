package com.jonbj.alembic.monitor.feature.performance

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.data.repository.PerformanceRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class PerformanceViewModel(
    private val repository: PerformanceRepository
) : ViewModel() {

    val state = repository.performance

    private val _selectedPeriod = MutableStateFlow(PerformancePeriod.DEFAULT)
    val selectedPeriod: StateFlow<PerformancePeriod> = _selectedPeriod.asStateFlow()
    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()
    private var activeRefreshes = 0

    init {
        refresh()
    }

    fun selectPeriod(period: PerformancePeriod) {
        if (period != _selectedPeriod.value) {
            _selectedPeriod.value = period
            refresh()
        }
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            activeRefreshes += 1
            _isRefreshing.value = true
            try {
                repository.refresh(_selectedPeriod.value.apiValue, force)
            } finally {
                activeRefreshes -= 1
                _isRefreshing.value = activeRefreshes > 0
            }
        }
    }
}
