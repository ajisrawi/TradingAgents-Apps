# TradingAgents for Windows and Android

Standalone apps around the [TradingAgents](https://github.com/TauricResearch/TradingAgents)
multi-agent trading research framework (Apache-2.0, by Tauric Research). Both apps run the
framework itself, unmodified: the Windows app in a bundled Python, the Android app in a Python
embedded in the APK. Neither needs the other, a server, or an account besides your LLM provider's.

This is an unofficial front end and is not affiliated with Tauric Research.

## Download

From the [latest release](../../releases/latest):

| | File | Install |
|---|---|---|
| Windows 10/11 (64-bit) | `TradingAgents-<version>-windows-x64.zip` | Unzip anywhere and run `TradingAgents.exe`. Keep the folder together. |
| Android 7+ (arm64) | `TradingAgents-<version>-arm64.apk` | Open it on the phone and allow installing from this source. |

The apps are not code-signed for a store, so Windows SmartScreen and Play Protect may ask you to confirm.

## Using it

1. Open **Settings** and paste the API key of the LLM provider you want (OpenAI, Anthropic,
   Google, DeepSeek, OpenRouter, ... or a local Ollama / OpenAI-compatible server, which needs none).
2. On **New analysis**, enter a ticker, pick the analysts, depth and models, and start.
3. **Live run** shows each agent's status and report as it lands, and the final rating.
   **History** keeps every finished analysis.

An analysis makes dozens of LLM calls and takes several minutes; your provider bills them to
your key. On Android a run continues with the screen off and notifies you when it ends.
Settings also has a light / dark appearance choice.

**Your keys stay on your device.** Nothing is built into the apps: a key you enter is stored
only on that device (encrypted for your Windows account with DPAPI on Windows, in the app's
private storage on Android) and is sent only to the provider it belongs to.

The output is research, not financial, investment or trading advice.

## Layout

- `TradingAgents/` — the upstream framework, as a git submodule.
- `app/tradingagents_app/` — the engine shared by both apps: runs the framework's agent graph
  on a worker thread and serves the UI (`web/`) and a small JSON/event API on `127.0.0.1` only.
  `desktop.py` is the Windows window; `android.py` is the entry point the Android app calls.
- `app/packaging/` — the Windows build (PyInstaller).
- `android/` — the Android project (Kotlin shell + [Chaquopy](https://chaquo.com/chaquopy/) for
  the embedded Python). `requirements.txt` pins the Python packages that go into the APK.

## Building from source

```powershell
git clone --recurse-submodules <this repository>
cd <its folder>
uv venv .venv --python 3.13
uv pip install --python .venv\Scripts\python.exe -e .\TradingAgents pywebview pyinstaller
```

Windows app, into `app\dist\TradingAgents\`:

```powershell
powershell -ExecutionPolicy Bypass -File app\packaging\build_windows.ps1
```

Android app (needs the Android SDK, JDK 17+ and Python 3.13 on the PATH as `py -3.13`; put the
SDK's location in `android\local.properties` as `sdk.dir=...` or set `ANDROID_HOME`):

```powershell
cd android
.\gradlew.bat assembleRelease                 # phones (arm64-v8a)
.\gradlew.bat assembleDebug -Pabis=x86_64     # the emulator
```

To run the engine from source with the UI in a browser:
`cd app; ..\.venv\Scripts\python -m tradingagents_app --server`, then open `http://127.0.0.1:8756/`.

## Updating the framework

Move the `TradingAgents` submodule to the new upstream commit, then rebuild. If its
dependencies changed, reinstall them into `.venv` for Windows, and for Android re-check
`android/requirements.txt` against the framework's `pyproject.toml` (the compiled packages must
stay on versions that have Android builds; the file's header says where those come from).

## Not included

The framework's backtest and portfolio-file commands, and the Amazon Bedrock provider, are
available from the upstream CLI only.

## Credits

[TradingAgents](https://github.com/TauricResearch/TradingAgents) by Tauric Research, Apache-2.0.
Android wheels for the compiled Python packages come from [Flet's package index](https://pypi.flet.dev).
