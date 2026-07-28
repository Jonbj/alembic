package com.jonbj.alembic.monitor.feature.portfolio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jonbj.alembic.monitor.data.repository.PortfolioRepository
import kotlinx.coroutines.launch

class PortfolioViewModel(
    private val repository: PortfolioRepository
) : ViewModel() {

    val state = repository.positions

    init {
        refresh()
    }

    fun refresh(force: Boolean = true) {
        viewModelScope.launch {
            repository.refresh(force)
        }
    }
}
