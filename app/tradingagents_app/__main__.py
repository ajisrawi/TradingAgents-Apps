"""Entry point on a PC: the desktop window, or with --server the engine alone."""

import argparse
import logging
import time
from logging.handlers import RotatingFileHandler

from tradingagents_app.paths import app_home, redirect_missing_streams


def configure_logging() -> None:
    handler = RotatingFileHandler(app_home() / "app.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _serve(port: int) -> None:
    from tradingagents_app.server import create_engine

    port = create_engine().start(port)
    print(f"TradingAgents engine: http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main() -> None:
    redirect_missing_streams()
    configure_logging()
    parser = argparse.ArgumentParser(prog="TradingAgents")
    parser.add_argument("--server", action="store_true",
                        help="run the engine without a window and open the UI in a browser yourself")
    parser.add_argument("--port", type=int, default=8756, help="local port for --server (default 8756)")
    args = parser.parse_args()

    if args.server:
        _serve(args.port)
    else:
        from tradingagents_app.desktop import main as desktop_main
        desktop_main()


if __name__ == "__main__":
    main()
