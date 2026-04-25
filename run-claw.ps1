#Requires -Version 5.1
<#
.SYNOPSIS
  Run the packaged ClawCodex `claw` CLI from this repo folder.

.DESCRIPTION
  Uses bin\windows\claw.exe. Pass any normal claw arguments after the script name,
  e.g.  .\run-claw.ps1 prompt "hello"   or   .\run-claw.ps1 --help

  Set at least one provider credential before use, for example:
    $env:ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClawExe = Join-Path $RepoRoot "bin\windows\claw.exe"

if (-not (Test-Path -LiteralPath $ClawExe)) {
    Write-Host "Missing: $ClawExe" -ForegroundColor Red
    Write-Host "Build it first:  .\build-claw.ps1" -ForegroundColor Yellow
    exit 1
}

$hasAuth =
    $env:ANTHROPIC_API_KEY -or $env:ANTHROPIC_AUTH_TOKEN -or
    $env:OPENAI_API_KEY -or $env:XAI_API_KEY -or $env:DASHSCOPE_API_KEY

if (-not $hasAuth) {
    Write-Host "No API key / token detected in the environment." -ForegroundColor Yellow
    Write-Host "Set one before running, for example (Anthropic):" -ForegroundColor Yellow
    Write-Host '  $env:ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"' -ForegroundColor Cyan
    Write-Host "OpenRouter-style example:" -ForegroundColor Yellow
    Write-Host '  $env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"' -ForegroundColor Cyan
    Write-Host '  $env:OPENAI_API_KEY = "YOUR_API_KEY_HERE"' -ForegroundColor Cyan
    Write-Host ""
}

& $ClawExe @args
