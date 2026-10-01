"""API keys saved from the Settings page.

On Windows the file is encrypted with DPAPI, so only the Windows account that
saved it can read it. Elsewhere it is a plain file readable by its owner only.
The framework reads its keys from the environment, so saved keys are exported
there; a key saved here wins over one the environment already had.
"""

import json
import os
import sys
import threading

from .paths import app_home

_lock = threading.Lock()
# What the environment held before any saved key was applied, so removing a
# saved key puts back the value it had replaced.
_original_env: dict[str, str | None] = {}

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def _dpapi(function, data: bytes) -> bytes:
        source = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                              ctypes.POINTER(ctypes.c_char)))
        result = _Blob()
        if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
            raise OSError("Windows could not process the saved keys (DPAPI)")
        try:
            return ctypes.string_at(result.pbData, result.cbData)
        finally:
            _kernel32.LocalFree(result.pbData)

    def _encode(data: bytes) -> bytes:
        return _dpapi(_crypt32.CryptProtectData, data)

    def _decode(data: bytes) -> bytes:
        return _dpapi(_crypt32.CryptUnprotectData, data)
else:
    def _encode(data: bytes) -> bytes:
        return data

    def _decode(data: bytes) -> bytes:
        return data


def _path():
    return app_home() / "keys.bin"


def _read() -> dict[str, str]:
    try:
        return json.loads(_decode(_path().read_bytes()).decode("utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # Unreadable (another account's file, or damaged): start empty rather
        # than refuse to start. The keys can be entered again.
        return {}


def _write(values: dict[str, str]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(_encode(json.dumps(values).encode("utf-8")))
    os.replace(tmp, path)


def apply_to_environ() -> None:
    """Export every saved key. Called once at startup."""
    with _lock:
        for name, value in _read().items():
            _original_env.setdefault(name, os.environ.get(name))
            os.environ[name] = value


def saved_names() -> set[str]:
    with _lock:
        return set(_read())


def set_value(name: str, value: str) -> None:
    """Save a key and export it; an empty value removes it."""
    with _lock:
        values = _read()
        _original_env.setdefault(name, os.environ.get(name))
        if value:
            values[name] = value
            os.environ[name] = value
        else:
            values.pop(name, None)
            original = _original_env.get(name)
            if original is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = original
        _write(values)
