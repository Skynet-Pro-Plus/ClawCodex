#Requires -Version 5.1
<#
  Optional launcher: set OpenRouter here, then run like run-claw.ps1.

  Edit the line below: replace the placeholder with your real OpenRouter API key.
  If you use a real key, do not push that edit to a public remote (treat it like a secret).

  Examples:
    .\run-claw.local.ps1 doctor
    .\run-claw.local.ps1 prompt "say hello"

  If execution policy blocks scripts:
    powershell -ExecutionPolicy Bypass -File .\run-claw.local.ps1 prompt "say hello"
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClawExe = Join-Path $RepoRoot "bin\windows\claw.exe"

if (-not (Test-Path -LiteralPath $ClawExe)) {
    Write-Host "Missing: $ClawExe" -ForegroundColor Red
    Write-Host "Build it first:  .\build-claw.ps1" -ForegroundColor Yellow
    exit 1
}

$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "PUT_YOUR_OPENROUTER_API_KEY_HERE"

Push-Location -LiteralPath $RepoRoot
try {
    & $ClawExe @args
} finally {
    Pop-Location
}
