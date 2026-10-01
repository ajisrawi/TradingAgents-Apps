"""Entry point inside the Android app, called from Kotlin once Python has started."""

import logging
import os

_engine = None
_port: int | None = None


def start() -> int:
    """Start the engine in this process and return the port its UI is served on.

    Safe to call again: the activity is recreated on rotation and on return
    from the background, while the process and its engine live on.
    """
    global _engine, _port
    if _port is None:
        # Python on Android cannot see the system's certificate store, which is
        # what some provider SDKs verify HTTPS against by default. Point them at
        # the bundle that ships with the app instead.
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())

        from .__main__ import configure_logging
        from .server import create_engine

        configure_logging()
        # Chaquopy sends stderr to Logcat, which is where a developer looks first.
        logging.getLogger().addHandler(logging.StreamHandler())
        _engine = create_engine()
        _port = _engine.start()
        logging.getLogger(__name__).info("Engine listening on 127.0.0.1:%d", _port)
    return _port


def is_running() -> bool:
    """Whether an analysis is in progress, for the service that keeps it alive."""
    session = _engine.runs.get() if _engine is not None else None
    return session is not None and session.status == "running"
