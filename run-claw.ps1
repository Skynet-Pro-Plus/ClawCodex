#Requires -Version 5.1
<#
.SYNOPSIS
  Run the packaged ClawCodex `claw` CLI from this repo folder.

.DESCRIPTION
  Uses bin\windows\claw.exe. Pass any normal claw arguments after the script name,
  e.g.  .\run-claw.ps1 prompt "hello"   or   .\run-claw.ps1 --help

  Set OpenRouter credentials before use (environment or repo-root .env):
    $env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
    $env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClawExe = Join-Path $RepoRoot "bin\windows\claw.exe"

if (-not (Test-Path -LiteralPath $ClawExe)) {
    Write-Host "Missing: $ClawExe" -ForegroundColor Red
    Write-Host "Build it first:  .\build-claw.ps1" -ForegroundColor Yellow
    exit 1
}

$base = $env:OPENAI_BASE_URL
$openrouterBaseOk = $false
if ($base) {
    $openrouterBaseOk = $base.ToLowerInvariant().Contains("openrouter")
}
$hasAuth = [bool]($env:OPENAI_API_KEY -and $openrouterBaseOk)

if (-not $hasAuth) {
    Write-Host "OpenRouter credentials not detected in the environment." -ForegroundColor Yellow
    Write-Host "Set both variables, or copy .env.example to .env in this repo folder." -ForegroundColor Yellow
    Write-Host '  $env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"' -ForegroundColor Cyan
    Write-Host '  $env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"' -ForegroundColor Cyan
    Write-Host ""
}

# Run with cwd = repo root so a repo-root .env is found even if you started this script from elsewhere.
Push-Location -LiteralPath $RepoRoot
try {
    & $ClawExe @args
} finally {
    Pop-Location
}
