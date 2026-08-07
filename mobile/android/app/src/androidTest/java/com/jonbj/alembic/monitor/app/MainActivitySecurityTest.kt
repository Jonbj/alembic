package com.jonbj.alembic.monitor.app

import android.view.WindowManager
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Verifies the debug variant's window-level screenshot policy. */
@RunWith(AndroidJUnit4::class)
class MainActivitySecurityTest {

    /** Confirms debug builds leave Android screenshots enabled. */
    @Test
    fun debugBuildAllowsScreenshots() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val secureFlag = activity.window.attributes.flags and
                    WindowManager.LayoutParams.FLAG_SECURE

                assertEquals(0, secureFlag)
            }
        }
    }
}
