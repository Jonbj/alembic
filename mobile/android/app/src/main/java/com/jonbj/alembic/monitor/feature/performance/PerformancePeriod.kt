package com.jonbj.alembic.monitor.feature.performance

import androidx.annotation.StringRes
import com.jonbj.alembic.monitor.R

enum class PerformancePeriod(
    val apiValue: String,
    @StringRes val labelRes: Int
) {
    ONE_WEEK("1w", R.string.period_1w),
    ONE_MONTH("1m", R.string.period_1m),
    THREE_MONTHS("3m", R.string.period_3m),
    SIX_MONTHS("6m", R.string.period_6m),
    ONE_YEAR("1y", R.string.period_1y),
    ALL("all", R.string.period_all);

    companion object {
        val DEFAULT = ONE_MONTH

        fun fromApiValue(value: String): PerformancePeriod =
            entries.firstOrNull { it.apiValue == value } ?: DEFAULT
    }
}
