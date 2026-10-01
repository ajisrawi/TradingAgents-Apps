package app.tradingagents.android

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * The Python engine, one per process. It serves the UI on a 127.0.0.1 port that
 * the activity's web view loads, and it outlives the activity.
 */
object Engine {
    private const val TAG = "TradingAgents"
    private const val MODULE = "tradingagents_app.android"

    private val main = Handler(Looper.getMainLooper())
    private val waiting = mutableListOf<(Result<Int>) -> Unit>()
    private var result: Result<Int>? = null
    private var starting = false

    /** Start the engine if needed and report its port, or the failure, on the main thread. */
    fun start(context: Context, callback: (Result<Int>) -> Unit) {
        result?.takeIf { it.isSuccess }?.let { callback(it); return }
        waiting += callback
        if (starting) return
        starting = true
        result = null

        val appContext = context.applicationContext
        Thread({
            val outcome = runCatching {
                if (!Python.isStarted()) Python.start(AndroidPlatform(appContext))
                Python.getInstance().getModule(MODULE).callAttr("start").toInt()
            }.onFailure { Log.e(TAG, "The engine failed to start", it) }
            main.post {
                starting = false
                result = outcome
                waiting.toList().also { waiting.clear() }.forEach { it(outcome) }
            }
        }, "engine-start").start()
    }

    /** Whether an analysis is in progress. Call off the main thread. */
    fun isRunning(): Boolean =
        result?.isSuccess == true &&
            runCatching { Python.getInstance().getModule(MODULE).callAttr("is_running").toBoolean() }
                .getOrDefault(false)
}
