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

    private val _selectedPeriod = MutableStateFlow("1m")
    val selectedPeriod: StateFlow<String> = _selectedPeriod.asStateFlow()

    init {
        refresh()
    }

    fun selectPeriod(period: String) {
        if (period != _selectedPeriod.value) {
            _selectedPeriod.value = period
            refresh()
        }
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            repository.refresh(_selectedPeriod.value, force)
        }
    }
}
