package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.ui.components.foregroundRefreshIntervalMillis
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class ForegroundRefreshCoordinator(
    private val statusRepository: StatusRepository,
    private val portfolioRepository: PortfolioRepository,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
) {
    private var pollingJob: Job? = null

    @Synchronized
    fun start() {
        if (pollingJob?.isActive == true) return
        pollingJob = scope.launch {
            while (isActive) {
                statusRepository.refresh()
                portfolioRepository.refresh()
                val pipelineExpected =
                    (statusRepository.snapshot.value as? LoadState.Success)
                        ?.data
                        ?.operational
                        ?.pipelineExpected
                        ?: true
                delay(foregroundRefreshIntervalMillis(pipelineExpected))
            }
        }
    }

    @Synchronized
    fun stop() {
        pollingJob?.cancel()
        pollingJob = null
    }
}
