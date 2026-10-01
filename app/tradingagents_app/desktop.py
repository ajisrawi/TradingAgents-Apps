"""The Windows application: the engine and its UI in a native window."""

import ctypes
import sys

import webview

from .paths import app_home
from .server import create_engine

TITLE = "TradingAgents"
# Held for the life of the process, so a second launch can tell one is running.
_instance_mutex = None


def _already_running() -> bool:
    global _instance_mutex
    if sys.platform != "win32":
        return False
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "TradingAgentsDesktopApp")
    return ctypes.windll.kernel32.GetLastError() == 183    # ERROR_ALREADY_EXISTS


def main() -> None:
    if _already_running():
        ctypes.windll.user32.MessageBoxW(None, "TradingAgents is already running.", TITLE, 0x40)
        return

    engine = create_engine()
    port = engine.start()

    window = webview.create_window(
        TITLE,
        f"http://127.0.0.1:{port}/",
        width=1320,
        height=880,
        min_size=(480, 600),
        background_color="#0c1118",
    )

    def confirm_close():
        """An analysis lives in this process, so closing the window ends it."""
        session = engine.runs.get()
        if session is not None and session.status == "running":
            return window.create_confirmation_dialog(
                TITLE, "An analysis is still running. Closing the app will stop it. Close anyway?")
        return True

    window.events.closing += confirm_close
    # A profile of its own, so the window does not start from a blank one each launch.
    webview.start(private_mode=False, storage_path=str(app_home() / "webview"))
