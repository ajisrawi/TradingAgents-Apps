# Builds the Windows application into app\dist\TradingAgents\TradingAgents.exe.
# Needs the project's virtual environment (.venv) with pyinstaller and pywebview installed.
$ErrorActionPreference = "Stop"
$app = Split-Path -Parent $PSScriptRoot
$python = Join-Path (Split-Path -Parent $app) ".venv\Scripts\python.exe"

& $python -m PyInstaller (Join-Path $PSScriptRoot "TradingAgents.spec") --noconfirm `
    --distpath (Join-Path $app "dist") --workpath (Join-Path $app "build")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built $(Join-Path $app 'dist\TradingAgents\TradingAgents.exe')"
