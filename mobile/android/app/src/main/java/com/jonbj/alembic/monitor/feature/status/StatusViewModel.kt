package com.jonbj.alembic.monitor.feature.status

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.app.di.AppModule
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.data.repository.StatusRepository
import kotlinx.coroutines.launch

class StatusViewModel(
    private val repository: StatusRepository = AppModule.statusRepository
) : ViewModel() {

    val state = repository.snapshot

    init {
        refresh()
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            repository.refresh(force)
        }
    }
}
