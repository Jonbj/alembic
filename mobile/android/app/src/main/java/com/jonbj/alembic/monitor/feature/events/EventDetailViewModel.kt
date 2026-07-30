package com.jonbj.alembic.monitor.feature.events

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.core.model.DataSource
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.data.repository.EventsRepository
import com.jonbj.alembic.monitor.push.OpaqueEventId
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class EventDetailViewModel(
    private val eventId: OpaqueEventId,
    private val repository: EventsRepository
) : ViewModel() {
    private val _state = MutableStateFlow<LoadState<EventItem>>(LoadState.Loading)
    val state: StateFlow<LoadState<EventItem>> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.value = LoadState.Loading
            val event = repository.findById(eventId)
            _state.value = if (event != null) {
                LoadState.Success(event, DataSource.NETWORK, 0)
            } else {
                LoadState.Error(
                    message = "Evento non disponibile",
                    retryable = true
                )
            }
        }
    }
}
