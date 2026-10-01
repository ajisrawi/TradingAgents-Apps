"""One analysis run: the framework's graph on a worker thread, reported as events.

A run belongs to the engine, not to a window. The desktop window and a paired
phone both follow it by reading its events from the start, so either can open
late, drop off and come back without losing anything.
"""

import logging
import os
import threading
import time
import traceback
import uuid

from cli.stats_handler import StatsCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from tradingagents.agents.rating import is_review, run_rating
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.api_key_env import get_api_key_env

from . import catalog

logger = logging.getLogger(__name__)

ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
RESEARCH_TEAM = ["Bull Researcher", "Bear Researcher", "Research Manager"]
RISK_TEAM = ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"]

TEAMS = [
    ("Analyst Team", [ANALYST_NODE_SPECS[key].agent_node for key in ANALYST_ORDER]),
    ("Research Team", RESEARCH_TEAM),
    ("Trading Team", ["Trader"]),
    ("Risk Management", RISK_TEAM),
    ("Portfolio Management", ["Portfolio Manager"]),
]

# Longest message body kept in the feed; a tool result can be a whole price history.
_MESSAGE_LIMIT = 4000
_TOOL_ARGS_LIMIT = 300


class RunError(ValueError):
    """A request that cannot be run, worded for the person who made it."""


class _Cancelled(Exception):
    pass


def build_request(payload: dict) -> dict:
    """Check a run request from the form and fill in what it leaves out."""
    try:
        ticker = catalog.parse_ticker(payload.get("ticker"))
        analysis_date = catalog.parse_date(payload.get("date"))
    except ValueError as exc:
        raise RunError(str(exc)) from None
    asset = catalog.asset_type(ticker)

    chosen = payload.get("analysts")
    if not isinstance(chosen, list):
        chosen = []
    analysts = [key for key in ANALYST_ORDER if key in chosen]
    if asset == "crypto":
        analysts = [key for key in analysts if key != "fundamentals"]
    if not analysts:
        raise RunError("Select at least one analyst.")

    try:
        depth = int(payload.get("depth", 1))
    except (TypeError, ValueError):
        raise RunError("Research depth must be a number.") from None
    if not 1 <= depth <= 5:
        raise RunError("Research depth must be between 1 and 5.")

    provider = str(payload.get("provider") or "").lower()
    if provider not in catalog.provider_keys():
        raise RunError("Choose an LLM provider.")

    models = {}
    for mode in ("quick", "deep"):
        model = str(payload.get(f"{mode}_model") or "").strip()
        if not model or model == "custom" or len(model) > 200:
            raise RunError(f"Choose the {mode}-thinking model.")
        models[mode] = model

    backend_url = DEFAULT_CONFIG.get("backend_url") or catalog.default_url(provider)
    if catalog.url_editable(provider):
        entered = str(payload.get("backend_url") or "").strip()
        if entered:
            if not entered.startswith(("http://", "https://")):
                raise RunError("The server URL must start with http:// or https://")
            backend_url = entered
        if not backend_url:
            raise RunError("Enter the URL of your OpenAI-compatible server, e.g. http://localhost:1234/v1")

    key_env = get_api_key_env(provider)
    if key_env and not catalog.key_optional(provider) and not os.environ.get(key_env):
        raise RunError(f"No API key for this provider yet. Add {key_env} on the Settings page.")

    effort = None
    spec = next(p for p in catalog.providers() if p["key"] == provider)["effort"]
    if spec:
        effort = payload.get("effort") or None
        if effort is not None and effort not in {o["value"] for o in spec["options"]}:
            raise RunError(f"Unknown {spec['label'].lower()}.")

    language = str(payload.get("language") or "English").strip()[:40] or "English"

    return {
        "ticker": ticker,
        "asset_type": asset,
        "date": analysis_date,
        "analysts": analysts,
        "depth": depth,
        "provider": provider,
        "quick_model": models["quick"],
        "deep_model": models["deep"],
        "backend_url": backend_url,
        "effort": effort,
        "language": language,
        "checkpoint": bool(payload.get("checkpoint")),
    }


def build_config(request: dict) -> dict:
    """The framework config for a request, as the CLI assembles it from its prompts."""
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = request["depth"]
    config["max_risk_discuss_rounds"] = request["depth"]
    config["llm_provider"] = request["provider"]
    config["quick_think_llm"] = request["quick_model"]
    config["deep_think_llm"] = request["deep_model"]
    config["backend_url"] = request["backend_url"]
    config["output_language"] = request["language"]
    config["checkpoint_enabled"] = request["checkpoint"]
    for provider, key in (("google", "google_thinking_level"),
                          ("openai", "openai_reasoning_effort"),
                          ("anthropic", "anthropic_effort")):
        if request["provider"] == provider:
            config[key] = request["effort"]
    return config


def _text(content) -> str | None:
    """The text of a message's content, whichever shape the provider returned."""
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, dict):
        return _text(content.get("text"))
    if isinstance(content, list):
        parts = [_text(item) if isinstance(item, str)
                 else _text(item.get("text")) if isinstance(item, dict) and item.get("type") == "text"
                 else None
                 for item in content]
        return " ".join(p for p in parts if p) or None
    return None if content is None else str(content).strip() or None


def _kind(message) -> str:
    if isinstance(message, HumanMessage):
        return "User"
    if isinstance(message, ToolMessage):
        return "Data"
    if isinstance(message, AIMessage):
        return "Agent"
    return "System"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _FeedLogHandler(logging.Handler):
    """Shows the framework's warnings in the run's feed, where its user can see them."""

    def __init__(self, session):
        super().__init__(level=logging.WARNING)
        self.session = session

    def emit(self, record):
        try:
            self.session.message("System", record.getMessage())
        except Exception:
            self.handleError(record)


class RunSession:
    def __init__(self, request: dict):
        self.id = uuid.uuid4().hex[:12]
        self.request = request
        self.status = "running"
        self.started_at = time.time()
        self.finished_at: float | None = None
        self._events: list[dict] = []
        self._changed = threading.Condition()
        self._cancel = threading.Event()
        self._seen_messages: set = set()
        self._agent_status: dict[str, str] = {}
        self._reports: dict[str, str] = {}
        self._stats: dict | None = None

        selected = {ANALYST_NODE_SPECS[key].agent_node for key in request["analysts"]}
        for team, agents in TEAMS:
            for agent in agents:
                if team != "Analyst Team" or agent in selected:
                    self._agent_status[agent] = "pending"

    # -- events ---------------------------------------------------------------

    def _emit(self, kind: str, /, **data) -> None:
        with self._changed:
            self._events.append({"seq": len(self._events) + 1, "type": kind, **data})
            self._changed.notify_all()

    def _end(self, status: str, kind: str, /, **data) -> None:
        """Close the run with its last event; a reader sees both or neither."""
        with self._changed:
            self.finished_at = time.time()
            self.status = status
            self._emit(kind, **data)

    def events_after(self, seq: int, timeout: float) -> list[dict]:
        """Events past ``seq``, waiting up to ``timeout`` seconds for the first."""
        with self._changed:
            if len(self._events) <= seq and self.status == "running":
                self._changed.wait(timeout)
            return self._events[seq:]

    def message(self, kind: str, text: str) -> None:
        self._emit("message", time=time.strftime("%H:%M:%S"), kind=kind, text=_clip(text, _MESSAGE_LIMIT))

    def _set_status(self, agent: str, status: str) -> None:
        if agent in self._agent_status and self._agent_status[agent] != status:
            self._agent_status[agent] = status
            self._emit("status", agent=agent, status=status)

    def _advance(self, agent: str, status: str) -> None:
        """Move an agent forward; a finished agent stays finished."""
        if self._agent_status.get(agent) != "completed":
            self._set_status(agent, status)

    def _report(self, section: str, text: str) -> None:
        if text and self._reports.get(section) != text:
            self._reports[section] = text
            self._emit("report", section=section, text=text)

    def _emit_stats(self, handler) -> None:
        stats = handler.get_stats()
        if stats != self._stats:
            self._stats = stats
            self._emit("stats", **stats)

    def summary(self) -> dict:
        public = {k: v for k, v in self.request.items() if k != "backend_url"}
        return {
            "id": self.id,
            "status": self.status,
            "started_at": int(self.started_at * 1000),
            "finished_at": int(self.finished_at * 1000) if self.finished_at else None,
            "request": public,
            "teams": [{"name": team, "agents": [a for a in agents if a in self._agent_status]}
                      for team, agents in TEAMS],
        }

    def cancel(self) -> None:
        if self.status == "running" and not self._cancel.is_set():
            self._cancel.set()
            self.message("System", "Stopping after the current step…")

    # -- the run --------------------------------------------------------------

    def run(self) -> None:
        handler = _FeedLogHandler(self)
        framework_log = logging.getLogger("tradingagents")
        framework_log.addHandler(handler)
        try:
            self._execute()
        except _Cancelled:
            self._end("cancelled", "cancelled")
        except Exception as exc:
            logger.error("Run %s failed:\n%s", self.id, traceback.format_exc())
            for agent, status in list(self._agent_status.items()):
                if status == "in_progress":
                    self._set_status(agent, "error")
            self._end("error", "error", message=f"{type(exc).__name__}: {exc}")
        finally:
            framework_log.removeHandler(handler)

    def _check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise _Cancelled

    def _execute(self) -> None:
        request = self.request
        ticker, trade_date, asset = request["ticker"], request["date"], request["asset_type"]
        config = build_config(request)
        stats = StatsCallbackHandler()

        self.message("System", f"Analyzing {ticker} as of {trade_date}"
                               + (f" ({asset})" if asset != "stock" else ""))
        graph = TradingAgentsGraph(request["analysts"], config=config, debug=False, callbacks=[stats])

        # The same starting state the CLI builds: earlier decisions for this
        # ticker settled, their lessons and the instrument's identity included.
        self.message("System", "Preparing: settling earlier decisions and resolving the instrument")
        state = graph.create_run_state(ticker, trade_date, asset)
        self._check_cancelled()

        args = graph.propagator.get_graph_args(callbacks=[stats])
        thread = graph.begin_checkpoint(ticker, trade_date, asset)
        final_state: dict = {}
        try:
            if thread is not None:
                args["config"].setdefault("configurable", {})["thread_id"] = thread
                self.message("System", "Resuming the saved run" if getattr(graph, "_resuming", False)
                             else "Checkpointing is on: this run can be resumed if it stops")

            for key in request["analysts"]:
                self._set_status(ANALYST_NODE_SPECS[key].agent_node, "in_progress")

            stream = graph.stream_run(graph.checkpoint_input(state), **args)
            try:
                for messages, chunk in stream:
                    self._check_cancelled()
                    self._on_messages(messages)
                    if chunk is not None:
                        final_state.update(chunk)
                        self._on_state(chunk, config)
                    self._emit_stats(stats)
            finally:
                stream.close()

            graph.record_decision(ticker, trade_date, final_state)
            graph.clear_checkpoint_on_success(ticker, trade_date, asset)
        finally:
            graph.end_checkpoint()

        for agent in self._agent_status:
            self._set_status(agent, "completed")
        self._emit_stats(stats)

        report_path = None
        try:
            report_path = str(graph.save_reports(final_state, ticker).parent)
        except Exception as exc:
            self.message("System", f"The report could not be saved to disk: {exc}")

        rating = run_rating(final_state)
        self._end("completed", "done", rating=rating, review=is_review(rating), report_path=report_path)

    def _on_messages(self, messages) -> None:
        for message in messages:
            key = getattr(message, "id", None) or (type(message).__name__, str(getattr(message, "content", "")))
            if key in self._seen_messages:
                continue
            self._seen_messages.add(key)

            text = _text(getattr(message, "content", None))
            if text:
                self.message(_kind(message), text)
            for call in getattr(message, "tool_calls", None) or []:
                name = call["name"] if isinstance(call, dict) else call.name
                call_args = call["args"] if isinstance(call, dict) else call.args
                self._emit("tool", time=time.strftime("%H:%M:%S"), name=name,
                           args=_clip(str(call_args), _TOOL_ARGS_LIMIT))

    def _on_state(self, chunk: dict, config: dict) -> None:
        """Turn a step's state into report and status events.

        ``chunk`` is the whole run state after a top-level step, or one
        analyst's report as soon as that analyst files it.
        """
        analysts = [ANALYST_NODE_SPECS[key] for key in self.request["analysts"]]
        for spec in analysts:
            if chunk.get(spec.report_key):
                self._report(spec.report_key, chunk[spec.report_key])
                self._set_status(spec.agent_node, "completed")

        debate = chunk.get("investment_debate_state") or {}
        bull = (debate.get("bull_history") or "").strip()
        bear = (debate.get("bear_history") or "").strip()
        plan = (chunk.get("investment_plan") or "").strip()
        trader = (chunk.get("trader_investment_plan") or "").strip()
        risk = chunk.get("risk_debate_state") or {}
        decision = (chunk.get("final_trade_decision") or "").strip()

        analysts_done = (bool(bull or bear or plan)
                         or all(self._reports.get(spec.report_key) for spec in analysts))
        if analysts_done:
            for spec in analysts:
                self._set_status(spec.agent_node, "completed")

        # Research team: bull and bear debate, then the manager rules.
        self._report("bull_history", bull)
        self._report("bear_history", bear)
        if plan:
            self._report("investment_plan", plan)
            for agent in RESEARCH_TEAM:
                self._set_status(agent, "completed")
            self._advance("Trader", "in_progress")
        elif analysts_done:
            if debate.get("count", 0) >= 2 * config["max_debate_rounds"]:
                self._set_status("Bull Researcher", "completed")
                self._set_status("Bear Researcher", "completed")
                self._advance("Research Manager", "in_progress")
            else:
                self._advance("Bull Researcher", "in_progress")
                if bull:
                    self._advance("Bear Researcher", "in_progress")

        # Trader, then the risk team's debate, then the portfolio manager.
        if trader:
            self._report("trader_investment_plan", trader)
            self._set_status("Trader", "completed")
        for section in ("aggressive_history", "conservative_history", "neutral_history"):
            self._report(section, (risk.get(section) or "").strip())
        if decision:
            self._report("final_trade_decision", decision)
            for agent in (*RISK_TEAM, "Portfolio Manager"):
                self._set_status(agent, "completed")
        elif trader:
            if risk.get("count", 0) >= 3 * config["max_risk_discuss_rounds"]:
                for agent in RISK_TEAM:
                    self._set_status(agent, "completed")
                self._advance("Portfolio Manager", "in_progress")
            else:
                for agent in RISK_TEAM:
                    self._advance(agent, "in_progress")


class RunManager:
    """Holds the current run. One runs at a time: the framework's data-vendor
    config is process-wide, and parallel runs would also multiply provider
    rate-limit pressure."""

    def __init__(self):
        self._lock = threading.Lock()
        self.current: RunSession | None = None

    def start(self, payload: dict) -> RunSession:
        request = build_request(payload)
        with self._lock:
            if self.current is not None and self.current.status == "running":
                raise RunError("An analysis is already running. Wait for it to finish or stop it.")
            session = RunSession(request)
            self.current = session
        threading.Thread(target=session.run, name=f"run-{session.id}", daemon=True).start()
        return session

    def get(self, run_id: str | None = None) -> RunSession | None:
        session = self.current
        if session is not None and run_id not in (None, session.id):
            return None
        return session
