#Requires -Version 5.1
<#
.SYNOPSIS
  Run the packaged ClawCodex `claw` CLI from this repo folder.

.DESCRIPTION
  Uses bin\windows\claw.exe. Pass any normal claw arguments after the script name,
  e.g.  .\run-claw.ps1 prompt "hello"   or   .\run-claw.ps1 --help

  Credentials: put OpenRouter settings in a repo-root `.env` (copy from .env.example).
  Optional: set OPENAI_BASE_URL and OPENAI_API_KEY in the shell instead (CI/advanced).
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
$hasAuthFromEnv = [bool]($env:OPENAI_API_KEY -and $openrouterBaseOk)
$dotenvPath = Join-Path $RepoRoot ".env"
$hasDotenvFile = Test-Path -LiteralPath $dotenvPath

if (-not $hasAuthFromEnv -and -not $hasDotenvFile) {
    Write-Host "OpenRouter: no credentials yet." -ForegroundColor Yellow
    Write-Host "  One place only: copy .env.example to .env in this repo folder, edit OPENAI_API_KEY once, then run this script again." -ForegroundColor Yellow
    Write-Host "  (Advanced: set OPENAI_BASE_URL + OPENAI_API_KEY in your shell instead of using .env.)" -ForegroundColor DarkGray
    Write-Host ""
}

# Run with cwd = repo root so repo-root .env is found even if you started this script from elsewhere.
Push-Location -LiteralPath $RepoRoot
try {
    & $ClawExe @args
} finally {
    Pop-Location
}
