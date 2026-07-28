package com.jonbj.alembic.monitor.feature.status

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.data.repository.StatusRepository
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class StatusViewModel(
    private val repository: StatusRepository
) : ViewModel() {

    val state = repository.snapshot
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
