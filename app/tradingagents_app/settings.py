"""The app's own settings: the choices last used on the run form, and how the UI looks."""

import copy
import json
import os
import threading

from .paths import app_home

_SECTIONS = ("prefs", "ui")

_lock = threading.RLock()
_cache: dict | None = None


def _path():
    return app_home() / "settings.json"


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            stored = json.loads(_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        _cache = {name: stored[name] if isinstance(stored.get(name), dict) else {} for name in _SECTIONS}
    return _cache


def _save() -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_cache, f, indent=2)
    os.replace(tmp, path)


def get(section: str) -> dict:
    with _lock:
        return copy.deepcopy(_load()[section])


def replace(section: str, value: dict) -> None:
    with _lock:
        _load()[section] = copy.deepcopy(value)
        _save()
