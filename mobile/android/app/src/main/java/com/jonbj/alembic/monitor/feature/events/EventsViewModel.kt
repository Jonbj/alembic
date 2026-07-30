package com.jonbj.alembic.monitor.feature.events

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.data.repository.EventsRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class EventFilter(val apiValue: String) {
    ALL("all"),
    CRITICAL("critical"),
    TRADING("trading"),
    SYSTEM("system")
}

class EventsViewModel(
    private val repository: EventsRepository
) : ViewModel() {

    val state = repository.events

    private val _selectedCategory = MutableStateFlow(EventFilter.ALL)
    val selectedCategory: StateFlow<EventFilter> = _selectedCategory.asStateFlow()
    private val _selectedDays = MutableStateFlow(EventsRepository.DEFAULT_DAYS)
    val selectedDays: StateFlow<Int> = _selectedDays.asStateFlow()
    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()
    private val _isLoadingNext = MutableStateFlow(false)
    val isLoadingNext: StateFlow<Boolean> = _isLoadingNext.asStateFlow()

    init {
        refresh()
    }

    fun selectCategory(category: EventFilter) {
        if (category != _selectedCategory.value) {
            _selectedCategory.value = category
            refresh()
        }
    }

    fun selectDays(days: Int) {
        if (days != _selectedDays.value) {
            _selectedDays.value = days.coerceAtMost(EventsRepository.MAX_DAYS)
            refresh()
        }
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                repository.refresh(
                    category = _selectedCategory.value.apiValue,
                    days = _selectedDays.value,
                    force = force
                )
            } finally {
                _isRefreshing.value = false
            }
        }
    }

    fun loadNext() {
        if (_isLoadingNext.value) return
        viewModelScope.launch {
            _isLoadingNext.value = true
            try {
                repository.loadNext()
            } finally {
                _isLoadingNext.value = false
            }
        }
    }
}
