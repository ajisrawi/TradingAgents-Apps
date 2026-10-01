"""Past runs, read from the state logs the framework writes for every finished run.

These are the same files a CLI run leaves under the results directory, so runs
made from the command line show up here too.
"""

import json
import re
from pathlib import Path

from tradingagents.agents.rating import run_rating
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG

_LOG_NAME = re.compile(r"^full_states_log_(\d{4}-\d{2}-\d{2})\.json$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Parsed summaries by path, valid while the file's modification time holds.
_cache: dict[Path, tuple[float, dict]] = {}


def _results_dir() -> Path:
    return Path(DEFAULT_CONFIG["results_dir"])


def _summary(path: Path, date: str) -> dict | None:
    mtime = path.stat().st_mtime
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    settings = entry.get("run_settings") or {}
    summary = {
        "ticker": entry.get("company_of_interest") or path.parent.parent.name,
        "date": date,
        "rating": entry.get("final_rating") or run_rating(entry),
        "saved_at": int(mtime * 1000),
        "provider": settings.get("llm_provider"),
        "deep_model": settings.get("deep_think_llm"),
        "quick_model": settings.get("quick_think_llm"),
    }
    _cache[path] = (mtime, summary)
    return summary


def list_runs() -> list[dict]:
    """Every saved run, most recently saved first."""
    runs = []
    for path in _results_dir().glob("*/TradingAgentsStrategy_logs/full_states_log_*.json"):
        match = _LOG_NAME.match(path.name)
        if match and (summary := _summary(path, match.group(1))):
            runs.append(summary)
    runs.sort(key=lambda r: r["saved_at"], reverse=True)
    return runs


def load_run(ticker: str, date: str) -> dict | None:
    """One saved run's reports, in the sections the live view uses."""
    if not _DATE.fullmatch(date or ""):
        return None
    try:
        component = safe_ticker_component(ticker)
    except ValueError:
        return None
    path = _results_dir() / component / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    debate = entry.get("investment_debate_state") or {}
    risk = entry.get("risk_debate_state") or {}
    reports = {
        "market_report": entry.get("market_report"),
        "sentiment_report": entry.get("sentiment_report"),
        "news_report": entry.get("news_report"),
        "fundamentals_report": entry.get("fundamentals_report"),
        "bull_history": debate.get("bull_history"),
        "bear_history": debate.get("bear_history"),
        "investment_plan": entry.get("investment_plan"),
        "trader_investment_plan": entry.get("trader_investment_plan"),
        "aggressive_history": risk.get("aggressive_history"),
        "conservative_history": risk.get("conservative_history"),
        "neutral_history": risk.get("neutral_history"),
        "final_trade_decision": entry.get("final_trade_decision"),
    }
    return {
        "ticker": entry.get("company_of_interest") or ticker,
        "date": date,
        "rating": entry.get("final_rating") or run_rating(entry),
        "settings": entry.get("run_settings") or {},
        "reports": {k: v for k, v in reports.items() if v},
    }
