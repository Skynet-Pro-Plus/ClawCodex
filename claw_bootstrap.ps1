# PowerShell bootstrap for the optional ClawCodex Python surface.
# Creates/reuses a repo-local .venv, installs requirements only when
# requirements.txt actually changed, then runs the FastAPI server (default)
# or the chat CLI ("chat" argument). Never touches WSL or the claw.exe pipeline.

$ErrorActionPreference = "Stop"

# Resolve the repo root from this script's location: no hardcoded drive paths.
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $RepoRoot

$Requirements = Join-Path $RepoRoot "requirements.txt"
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$StampFile = Join-Path $VenvDir ".requirements.sha256"

if (-not (Test-Path -LiteralPath $Requirements)) {
    Write-Host "[bootstrap] ERROR: requirements.txt not found at $Requirements" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "[bootstrap] Creating virtual environment in .venv..."
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host "[bootstrap] ERROR: could not create .venv (is Python 3 on PATH as 'python'?)" -ForegroundColor Red
        exit 1
    }
}

# Skip pip entirely when requirements.txt is unchanged since the last install.
$currentHash = (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash
$savedHash = ""
if (Test-Path -LiteralPath $StampFile) {
    $savedHash = (Get-Content -LiteralPath $StampFile -TotalCount 1).Trim()
}

if ($currentHash -ne $savedHash) {
    Write-Host "[bootstrap] requirements.txt changed - installing dependencies into .venv..."
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[bootstrap] ERROR: pip upgrade failed (exit $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[bootstrap] ERROR: dependency install failed (exit $LASTEXITCODE); not caching this attempt." -ForegroundColor Red
        exit 1
    }
    Set-Content -LiteralPath $StampFile -Value $currentHash -Encoding Ascii
}
else {
    Write-Host "[bootstrap] Dependencies are up to date (.venv cache hit)."
}

if ($args.Count -eq 0 -or $args[0] -eq "server") {
    Write-Host "[bootstrap] Starting FastAPI server on http://127.0.0.1:8000 ..."
    & $VenvPython -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000
    exit $LASTEXITCODE
}

if ($args[0] -eq "chat") {
    Write-Host "[bootstrap] Starting ClawCodex chat CLI..."
    & $VenvPython clawcodex_chat.py
    exit $LASTEXITCODE
}

Write-Error "Unknown argument: $($args[0]). Use 'server' (default) or 'chat'."
exit 1
