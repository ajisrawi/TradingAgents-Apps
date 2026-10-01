"""The engine's HTTP interface: the UI's files, a JSON API and the run's event stream.

It listens on 127.0.0.1 only. The Windows window and the Android app each load
the UI from it inside their own web view; nothing is reachable from the network.
"""

import json
import logging
import mimetypes
import sys
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import tradingagents

from . import __version__, catalog, history, secrets_store, settings
from .paths import web_dir
from .runs import RunError, RunManager

logger = logging.getLogger(__name__)

_MAX_BODY = 1 << 20
_TERMINAL_EVENTS = {"done", "error", "cancelled"}

_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                               "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache",
}


class _Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def platform_name() -> str:
    """'android', 'windows' or 'other': the UI words a few things per platform."""
    if hasattr(sys, "getandroidapilevel"):
        return "android"
    return "windows" if sys.platform == "win32" else "other"


def themes() -> tuple[str, ...]:
    """The appearance choices, the default first.

    A PC can follow the system's light or dark setting. The Android app has a
    look of its own rather than the system's, so there the choice is explicit.
    """
    return ("dark", "light") if platform_name() == "android" else ("system", "dark", "light")


def current_theme() -> str:
    theme = settings.get("ui").get("theme")
    return theme if theme in themes() else themes()[0]


class Engine:
    """The run manager and the listener that serves it."""

    def __init__(self):
        self.runs = RunManager()
        self.server: ThreadingHTTPServer | None = None
        self.static_files = self._index_static()

    @staticmethod
    def _index_static() -> dict[str, tuple[bytes, str]]:
        """Every UI file, read once. Requests are answered from this table only."""
        root = web_dir()
        files = {}
        for path in root.rglob("*"):
            if path.is_file():
                kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                    kind += "; charset=utf-8"
                files["/" + path.relative_to(root).as_posix()] = (path.read_bytes(), kind)
        return files

    def start(self, port: int = 0) -> int:
        """Listen on 127.0.0.1 and return the port (``0`` picks a free one)."""
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        server.daemon_threads = True
        server.engine = self
        threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
        self.server = server
        return server.server_address[1]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "TradingAgentsApp"
    sys_version = ""

    def log_message(self, format, *args):
        logger.debug("%s %s", self.address_string(), format % args)

    @property
    def engine(self) -> Engine:
        return self.server.engine

    # -- plumbing -------------------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise _Refused(415, "Requests must be JSON.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise _Refused(400, "Bad request.") from None
        if not 0 <= length <= _MAX_BODY:
            raise _Refused(413, "Request too large.")
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise _Refused(400, "Bad request.") from None
        if not isinstance(payload, dict):
            raise _Refused(400, "Bad request.")
        return payload

    def _check_origin(self) -> None:
        """Refuse requests another website could have made a browser send.

        The engine answers only to its own address, which defeats a hostile
        page that points a hostname of its own at 127.0.0.1. A request that
        changes something must also come from this origin.
        """
        host = self.headers.get("Host", "")
        if host.rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
            raise _Refused(403, "Forbidden.")
        origin = self.headers.get("Origin")
        if self.command == "POST" and origin and urlsplit(origin).netloc != host:
            raise _Refused(403, "Forbidden.")

    # -- dispatch -------------------------------------------------------------

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self) -> None:
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            self._check_origin()
            if self.command == "POST":
                self._post(url.path)
            else:
                self._get(url.path, query)
        except _Refused as refusal:
            self._json({"error": refusal.message}, refusal.status)
        except RunError as exc:
            self._json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionError):
            self.close_connection = True
        except Exception:
            logger.exception("Request failed: %s %s", self.command, url.path)
            self._json({"error": "Something went wrong in the engine. See app.log."}, 500)

    def _static(self, path: str) -> None:
        entry = self.engine.static_files.get(path)
        if entry is None:
            raise _Refused(404, "Not found.")
        body = entry[0]
        theme = current_theme()
        if path == "/index.html" and theme != "system":
            # Written into the page itself, so it opens in the chosen colors
            # instead of switching to them once its script has run.
            body = body.replace(b"<html ", b'<html data-theme="%s" ' % theme.encode(), 1)
        self._send(200, body, entry[1])

    def _get(self, path: str, query: dict) -> None:
        engine = self.engine
        if path == "/api/bootstrap":
            self._json(self._bootstrap())
        elif path == "/api/run":
            session = engine.runs.get()
            self._json({"run": session.summary() if session else None})
        elif path == "/api/run/events":
            self._events(query)
        elif path == "/api/history":
            self._json({"runs": history.list_runs()})
        elif path == "/api/history/run":
            run = history.load_run(query.get("ticker", ""), query.get("date", ""))
            if run is None:
                raise _Refused(404, "That run is no longer on disk.")
            self._json(run)
        elif path == "/api/openrouter-models":
            try:
                self._json({"models": catalog.openrouter_models()})
            except Exception as exc:
                raise _Refused(502, f"Could not load the OpenRouter model list: {exc}") from None
        elif path.startswith("/api/"):
            raise _Refused(404, "Not found.")
        else:
            self._static("/index.html" if path == "/" else path)

    def _post(self, path: str) -> None:
        engine = self.engine
        body = self._body()
        if path == "/api/run":
            session = engine.runs.start(body)
            request = session.request
            settings.replace("prefs", {
                k: request[k] for k in ("ticker", "analysts", "depth", "provider", "quick_model",
                                        "deep_model", "effort", "language", "checkpoint")
            } | ({"backend_url": request["backend_url"]} if catalog.url_editable(request["provider"]) else {}))
            self._json({"run": session.summary()})
        elif path == "/api/run/cancel":
            session = engine.runs.get()
            if session is not None:
                session.cancel()
            self._json({"ok": True})
        elif path == "/api/settings/key":
            name = body.get("name")
            if name not in catalog.settable_names():
                raise _Refused(400, "Unknown setting.")
            secrets_store.set_value(name, str(body.get("value") or "").strip())
            self._json({"ok": True})
        elif path == "/api/settings/theme":
            if body.get("theme") not in themes():
                raise _Refused(400, "Unknown theme.")
            settings.replace("ui", {"theme": body["theme"]})
            self._json({"ok": True})
        else:
            raise _Refused(404, "Not found.")

    # -- responses ------------------------------------------------------------

    def _bootstrap(self) -> dict:
        session = self.engine.runs.get()
        return {
            "app_version": __version__,
            "framework_version": tradingagents.__version__,
            "platform": platform_name(),
            "themes": themes(),
            "theme": current_theme(),
            "now": int(time.time() * 1000),
            "today": date.today().isoformat(),
            "providers": catalog.providers(),
            "analysts": [{"key": k, "name": n, "hint": h} for k, n, h in catalog.ANALYSTS],
            "depths": [{"value": v, "name": n, "hint": h} for v, n, h in catalog.DEPTHS],
            "languages": catalog.LANGUAGES,
            "extra_settings": catalog.extra_settings(),
            "prefs": settings.get("prefs"),
            "run": session.summary() if session else None,
        }

    def _events(self, query: dict) -> None:
        """Stream a run's events from ``after`` on, as server-sent events."""
        session = self.engine.runs.get(query.get("id"))
        if session is None:
            raise _Refused(404, "That run is no longer in memory.")
        try:
            # A web view reconnecting on its own says where it had got to.
            seq = int(self.headers.get("Last-Event-ID") or query.get("after") or 0)
        except ValueError:
            seq = 0

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        while True:
            events = session.events_after(seq, timeout=15)
            if not events:
                if session.status != "running":
                    return
                self.wfile.write(b": waiting\n\n")
            for event in events:
                self.wfile.write(f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n".encode())
                seq = event["seq"]
            self.wfile.flush()
            if events and events[-1]["type"] in _TERMINAL_EVENTS:
                return


def create_engine() -> Engine:
    secrets_store.apply_to_environ()
    return Engine()
