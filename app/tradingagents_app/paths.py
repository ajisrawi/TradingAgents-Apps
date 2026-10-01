"""Where the app keeps its own files and finds its bundled ones."""

import os
import sys
from pathlib import Path


def app_home() -> Path:
    """Settings, saved keys and logs. Beside the framework's own ~/.tradingagents data."""
    home = Path(os.environ.get("TRADINGAGENTS_APP_HOME") or Path.home() / ".tradingagents" / "app")
    home.mkdir(parents=True, exist_ok=True)
    return home


def web_dir() -> Path:
    """The UI's static files, shipped inside the package on every platform."""
    return Path(__file__).resolve().parent / "web"


def redirect_missing_streams() -> None:
    """Give a windowed build somewhere to write.

    A windowed executable starts with no stdout or stderr, and a library that
    prints or logs to them would raise instead.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    log = open(app_home() / "app.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
