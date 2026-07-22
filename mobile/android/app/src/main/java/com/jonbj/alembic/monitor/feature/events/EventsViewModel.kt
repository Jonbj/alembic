package com.jonbj.alembic.monitor.feature.events

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.app.di.AppModule
import com.jonbj.alembic.monitor.data.repository.EventsRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class EventsViewModel(
    private val repository: EventsRepository = AppModule.eventsRepository
) : ViewModel() {

    val state = repository.events

    private val _selectedCategory = MutableStateFlow("all")
    val selectedCategory: StateFlow<String> = _selectedCategory.asStateFlow()

    init {
        refresh()
    }

    fun selectCategory(category: String) {
        if (category != _selectedCategory.value) {
            _selectedCategory.value = category
            refresh()
        }
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            repository.refresh(category = _selectedCategory.value, force = force)
        }
    }
}
