plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val abis = ((findProperty("abis") as String?) ?: "arm64-v8a").split(",")

android {
    namespace = "app.tradingagents.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.tradingagents.android"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        ndk {
            // The embedded Python and its packages are large, so an APK carries
            // one ABI: arm64-v8a, which is every current phone, unless the build
            // says otherwise, e.g. -Pabis=x86_64 for the emulator.
            abiFilters += abis
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Signed with the local debug key, so the APK installs as built. An
            // APK meant for a store needs a signing key of its own.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

// The Python that goes into the app: the framework from the upstream checkout
// and the engine shared with the Windows app, copied side by side.
val pythonSources = layout.buildDirectory.dir("python-src")
val syncPythonSources by tasks.registering(Sync::class) {
    from("../../TradingAgents") {
        include("tradingagents/**/*.py")
        // The engine uses the CLI's token counter and nothing else from it.
        include("cli/__init__.py", "cli/stats_handler.py")
    }
    from("../../app") {
        include("tradingagents_app/**")
        exclude("**/__pycache__/**", "tradingagents_app/desktop.py")
    }
    into(pythonSources)
}

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            options("--no-deps", "--extra-index-url", "https://pypi.flet.dev")
            install("-r", "../requirements.txt")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir(pythonSources)
        }
    }
}

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("PythonSources") }.configureEach {
    dependsOn(syncPythonSources)
}
