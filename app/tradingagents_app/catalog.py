"""What the run form offers: providers, models and the other choices.

The provider endpoints and the choices mirror the framework's CLI, and the
model lists come from the framework's own catalog, so a framework update that
adds models reaches the form without a change here.
"""

import os
import re
from datetime import date, datetime

import requests

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

from . import secrets_store

# (name shown, provider key, endpoint). The endpoints are the CLI's.
_PROVIDERS = [
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("Anthropic", "anthropic", "https://api.anthropic.com/"),
    ("Google Gemini", "google", None),
    ("xAI", "xai", "https://api.x.ai/v1"),
    ("DeepSeek", "deepseek", "https://api.deepseek.com"),
    ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
    ("Mistral", "mistral", "https://api.mistral.ai/v1"),
    ("Groq", "groq", "https://api.groq.com/openai/v1"),
    ("Qwen (International)", "qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    ("Qwen (China)", "qwen-cn", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("GLM (Z.AI, International)", "glm", "https://api.z.ai/api/paas/v4/"),
    ("GLM (BigModel, China)", "glm-cn", "https://open.bigmodel.cn/api/paas/v4/"),
    ("MiniMax (International)", "minimax", "https://api.minimax.io/v1"),
    ("MiniMax (China)", "minimax-cn", "https://api.minimaxi.com/v1"),
    ("Kimi (Moonshot)", "kimi", "https://api.moonshot.ai/v1"),
    ("NVIDIA NIM", "nvidia", "https://integrate.api.nvidia.com/v1"),
    ("Azure OpenAI", "azure", None),
    ("Ollama (local models)", "ollama", "http://localhost:11434/v1"),
    ("OpenAI-compatible server (LM Studio, vLLM, llama.cpp)", "openai_compatible", None),
]

_CUSTOM_ONLY = {"quick": [("Custom model ID", "custom")], "deep": [("Custom model ID", "custom")]}

# The provider-specific depth-of-reasoning choice: config key, label, options.
_EFFORT = {
    "openai": ("openai_reasoning_effort", "Reasoning effort",
               [("Medium (default)", "medium"), ("High (more thorough)", "high"), ("Low (faster)", "low")]),
    "anthropic": ("anthropic_effort", "Effort level",
                  [("High (recommended)", "high"), ("Medium (balanced)", "medium"),
                   ("Low (faster, cheaper)", "low")]),
    "google": ("google_thinking_level", "Thinking mode",
               [("Enable thinking (recommended)", "high"), ("Minimal thinking", "minimal")]),
}

ANALYSTS = [
    ("market", "Market Analyst", "Price action and technical indicators"),
    ("social", "Sentiment Analyst", "Social media and public sentiment"),
    ("news", "News Analyst", "Company and macro news"),
    ("fundamentals", "Fundamentals Analyst", "Financial statements and filings"),
]

DEPTHS = [
    (1, "Shallow", "Quick research, one round of debate"),
    (3, "Medium", "Moderate debate and risk discussion"),
    (5, "Deep", "Comprehensive research, in-depth debate"),
]

LANGUAGES = ["English", "Chinese", "Japanese", "Korean", "Hindi", "Spanish",
             "Portuguese", "French", "German", "Arabic", "Russian"]

# Keys beyond the LLM provider's own, shown on the Settings page.
EXTRA_SETTINGS = [
    ("FRED_API_KEY", "FRED API key", "Macro data for the News Analyst. Free at fred.stlouisfed.org.", True),
    ("ALPHA_VANTAGE_API_KEY", "Alpha Vantage API key", "Optional alternative market data vendor.", True),
    ("SEC_EDGAR_USER_AGENT", "SEC EDGAR contact", "Your name and email, sent to SEC with filings requests.", False),
    ("TYPESAFE_API_KEY", "TypeSafe API key", "Optional screening of social posts for the Sentiment Analyst.", True),
    ("AZURE_OPENAI_ENDPOINT", "Azure OpenAI endpoint", "https://<resource>.openai.azure.com/ (Azure only).", False),
    ("OPENAI_API_VERSION", "Azure OpenAI API version", "For example 2025-03-01-preview (Azure only).", False),
]

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
_TICKER_RE = re.compile(r"^[A-Za-z0-9._\-^=]{1,32}$")


def provider_keys() -> set[str]:
    return {key for _, key, _ in _PROVIDERS}


def default_url(provider: str) -> str | None:
    if provider == "ollama":
        return os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    return next((url for _, key, url in _PROVIDERS if key == provider), None)


def key_optional(provider: str) -> bool:
    spec = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    return get_api_key_env(provider) is None or bool(spec and spec.key_optional)


def url_editable(provider: str) -> bool:
    """Providers whose endpoint the user supplies or may change."""
    return provider in ("ollama", "openai_compatible")


def key_status(env_name: str | None, saved: set[str]) -> str:
    """Where a setting's value comes from: 'saved', 'environment' or 'missing'."""
    if not env_name:
        return "none"
    if env_name in saved:
        return "saved"
    return "environment" if os.environ.get(env_name) else "missing"


def providers() -> list[dict]:
    saved = secrets_store.saved_names()
    result = []
    for name, key, _ in _PROVIDERS:
        env_name = get_api_key_env(key)
        effort = _EFFORT.get(key)
        models = MODEL_OPTIONS.get(key, _CUSTOM_ONLY)
        result.append({
            "key": key,
            "name": name,
            "key_env": env_name,
            "key_status": key_status(env_name, saved),
            "key_optional": key_optional(key),
            "default_url": default_url(key),
            "url_editable": url_editable(key),
            "dynamic_models": key == "openrouter",
            "models": {mode: [{"label": label, "id": model_id} for label, model_id in models[mode]]
                       for mode in ("quick", "deep")},
            "effort": {"key": effort[0], "label": effort[1],
                       "options": [{"label": label, "value": value} for label, value in effort[2]]}
            if effort else None,
        })
    return result


def extra_settings() -> list[dict]:
    saved = secrets_store.saved_names()
    return [{"env": env, "label": label, "hint": hint, "secret": secret,
             "status": key_status(env, saved)}
            for env, label, hint, secret in EXTRA_SETTINGS]


def settable_names() -> set[str]:
    """Environment names the Settings page may write."""
    names = {get_api_key_env(key) for _, key, _ in _PROVIDERS}
    names.update(env for env, _, _, _ in EXTRA_SETTINGS)
    names.discard(None)
    return names


def parse_ticker(value) -> str:
    if not isinstance(value, str) or not _TICKER_RE.fullmatch(value.strip()):
        raise ValueError("Enter a ticker symbol such as NVDA, 0700.HK or BTC-USD.")
    return normalize_symbol(value)


def asset_type(ticker: str) -> str:
    return "crypto" if ticker.endswith(CRYPTO_SUFFIXES) else "stock"


def parse_date(value) -> str:
    try:
        day = datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Enter the analysis date as YYYY-MM-DD.") from None
    if day > date.today():
        raise ValueError("The analysis date cannot be in the future.")
    return day.isoformat()


# Chat-model namespaces worth listing first; the full OpenRouter list is long
# and its newest entries are mostly niche releases. Same shortlist as the CLI.
_OPENROUTER_MAINSTREAM = {
    "openai", "anthropic", "google", "deepseek", "qwen", "mistralai",
    "meta-llama", "x-ai", "z-ai", "minimax", "moonshotai",
}


def openrouter_models() -> list[dict]:
    """The newest mainstream OpenRouter models, newest first."""
    response = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
    response.raise_for_status()
    models = response.json().get("data", [])
    models.sort(key=lambda m: m.get("created") or 0, reverse=True)
    mainstream = [m for m in models
                  if not m["id"].startswith("~") and m["id"].split("/", 1)[0] in _OPENROUTER_MAINSTREAM]
    return [{"label": m.get("name") or m["id"], "id": m["id"]} for m in (mainstream or models)[:40]]
