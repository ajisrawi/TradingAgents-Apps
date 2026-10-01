# PyInstaller spec for the Windows application. Build with build_windows.ps1.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

APP = Path(SPECPATH).parent
FRAMEWORK = APP.parent / "TradingAgents"

datas = [(str(APP / "tradingagents_app" / "web"), "tradingagents_app/web")]
binaries = []
# The framework picks its provider clients and data vendors at run time.
hiddenimports = (
    collect_submodules("tradingagents")
    + ["cli", "cli.stats_handler", "tiktoken_ext", "tiktoken_ext.openai_public"]
)

# Packages that load their own data files or native libraries by path.
for package in ("curl_cffi", "yfinance", "stockstats", "langgraph", "sqlite_vec"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# Packages that read their own version from installed metadata.
for package in ("langchain-core", "langchain-openai", "langchain-anthropic", "langchain-google-genai",
                "langgraph", "openai", "anthropic", "google-genai", "yfinance", "curl_cffi", "tiktoken"):
    datas += copy_metadata(package)

a = Analysis(
    [str(APP / "launcher.py")],
    pathex=[str(APP), str(FRAMEWORK)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # The framework's Bedrock client needs langchain-aws, an optional extra that
    # the app does not offer; the CLI's terminal UI is not used either.
    excludes=["tradingagents.llm_clients.bedrock_client", "langchain_aws", "boto3", "botocore",
              "questionary", "prompt_toolkit", "typer", "tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="TradingAgents",
    icon=str(APP / "packaging" / "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="TradingAgents", upx=False)
