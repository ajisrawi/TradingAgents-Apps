package app.tradingagents.android

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView

/** The app's one screen: the engine's UI in a web view, behind a start-up overlay. */
class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var overlay: View
    private lateinit var status: TextView
    private lateinit var progress: ProgressBar
    private lateinit var retry: Button

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        webView = findViewById(R.id.web)
        overlay = findViewById(R.id.overlay)
        status = findViewById(R.id.status)
        progress = findViewById(R.id.progress)
        retry = findViewById(R.id.retry)
        retry.setOnClickListener { startEngine() }

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        // The theme last chosen in Settings, so the start-up screen already has its colors.
        applyTheme(getPreferences(MODE_PRIVATE).getString(PREF_THEME, null) == THEME_LIGHT)
        webView.addJavascriptInterface(Bridge(), "AndroidBridge")
        webView.webViewClient = object : WebViewClient() {
            // The web view shows the engine's own pages only; a link in a report
            // opens in the browser.
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (request.url.host == LOCALHOST) return false
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                } catch (_: ActivityNotFoundException) {
                }
                return true
            }

            override fun onPageFinished(view: WebView, url: String) {
                overlay.visibility = View.GONE
            }
        }
        startEngine()
    }

    private fun startEngine() {
        status.setText(R.string.starting)
        progress.visibility = View.VISIBLE
        retry.visibility = View.GONE
        Engine.start(this) { result ->
            if (isDestroyed) return@start
            result.onSuccess { port -> webView.loadUrl("http://$LOCALHOST:$port/") }
                .onFailure { error ->
                    status.text = getString(R.string.start_failed, error.message ?: error.toString())
                    progress.visibility = View.GONE
                    retry.visibility = View.VISIBLE
                }
        }
    }

    /** Color everything outside the page (system bars, start-up screen) to match the page's theme. */
    @Suppress("DEPRECATION")
    private fun applyTheme(light: Boolean) {
        val background = getColor(if (light) R.color.background_light else R.color.background)
        findViewById<View>(R.id.root).setBackgroundColor(background)
        overlay.setBackgroundColor(background)
        webView.setBackgroundColor(background)
        findViewById<TextView>(R.id.title).setTextColor(getColor(if (light) R.color.text_light else R.color.text))
        status.setTextColor(getColor(if (light) R.color.muted_light else R.color.muted))

        window.statusBarColor = background
        // Dark icons on a light bar. Before Android 8 the navigation bar's icons
        // cannot be darkened, so there that bar stays dark.
        var flags = window.decorView.systemUiVisibility and
            (View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR).inv()
        if (light) flags = flags or View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        if (Build.VERSION.SDK_INT >= 26) {
            window.navigationBarColor = background
            if (light) flags = flags or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
        window.decorView.systemUiVisibility = flags
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else moveTaskToBack(true)
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }

    /** What the page may ask of the app. Called on a web view thread. */
    private inner class Bridge {
        @JavascriptInterface
        fun setRunning(running: Boolean) = runOnUiThread {
            if (running) {
                if (Build.VERSION.SDK_INT >= 33 &&
                    checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                ) {
                    // So the "analysis finished" notice can be shown. The run goes on either way.
                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 0)
                }
                RunService.start(this@MainActivity)
            }
        }

        @JavascriptInterface
        fun setTheme(theme: String) = runOnUiThread {
            getPreferences(MODE_PRIVATE).edit().putString(PREF_THEME, theme).apply()
            applyTheme(theme == THEME_LIGHT)
        }

        @JavascriptInterface
        fun share(title: String, text: String) = runOnUiThread {
            val send = Intent(Intent.ACTION_SEND)
                .setType("text/plain")
                .putExtra(Intent.EXTRA_SUBJECT, title)
                .putExtra(Intent.EXTRA_TEXT, text)
            startActivity(Intent.createChooser(send, title))
        }
    }

    private companion object {
        const val LOCALHOST = "127.0.0.1"
        const val PREF_THEME = "theme"
        const val THEME_LIGHT = "light"
    }
}
