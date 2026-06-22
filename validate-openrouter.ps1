#Requires -Version 5.1
<#
.SYNOPSIS
  Terminal-friendly OpenRouter check for ClawCodex onboarding.

.DESCRIPTION
  - If no key or example placeholder: prints a clear yellow status and exits 10.
  - If a key is set: performs an authenticated GET to OpenRouter /v1/auth/key.
    This is free, model-agnostic, and works with normal OpenRouter keys. GET /v1/credits is
    management-key only and will 401 for standard keys.
    - 200: green "key accepted" and exit 0
    - 402: key is authenticated but account may be out of credits (still exit 0)
    - 401/403: red "key rejected" and exit 2 (blocks START-CLAW.bat until fixed)
    - Other/network: yellow warning and exit 3

  Credential resolution: repo-root .env wins over process environment when .env has a non-placeholder key,
  so a key you just saved is validated (stale OPENAI_API_KEY in the shell cannot override it).
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnv = Join-Path $RepoRoot ".env"

function Read-RepoDotEnv {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0) { return }
        if ($line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($value.Length -ge 2 -and $value.StartsWith("'") -and $value.EndsWith("'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $map[$name] = $value
    }
    return $map
}

$fileVars = Read-RepoDotEnv -Path $DotEnv

function Is-PlaceholderKey([string]$Value) {
    return [string]::IsNullOrWhiteSpace($Value) -or ($Value -eq "YOUR_OPENROUTER_KEY_HERE")
}

function Get-OpenRouterApiKey {
    $fileKey = $null
    if ($fileVars.ContainsKey("OPENAI_API_KEY")) {
        $fileKey = $fileVars["OPENAI_API_KEY"].Trim()
    }
    $procKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process")
    if ($null -ne $procKey) { $procKey = $procKey.Trim() }

    if (-not (Is-PlaceholderKey $fileKey)) {
        if ((-not (Is-PlaceholderKey $procKey)) -and ($fileKey -ne $procKey)) {
            Write-Host "  NOTE: OPENAI_API_KEY is set in both .env and this process; using .env for validation." -ForegroundColor DarkYellow
        }
        return $fileKey
    }
    if (-not (Is-PlaceholderKey $procKey)) { return $procKey }
    return $null
}

function Get-OpenRouterApiKeySource {
    $fileKey = $null
    if ($fileVars.ContainsKey("OPENAI_API_KEY")) {
        $fileKey = $fileVars["OPENAI_API_KEY"].Trim()
    }

    if (-not (Is-PlaceholderKey $fileKey)) { return ".env" }
    return "process env"
}

function Get-OpenRouterBaseUrl {
    $fileBase = $null
    if ($fileVars.ContainsKey("OPENAI_BASE_URL")) {
        $fileBase = $fileVars["OPENAI_BASE_URL"].Trim()
    }
    $procBase = [Environment]::GetEnvironmentVariable("OPENAI_BASE_URL", "Process")
    if ($null -ne $procBase) { $procBase = $procBase.Trim() }

    if (-not [string]::IsNullOrWhiteSpace($fileBase)) { return $fileBase }
    if (-not [string]::IsNullOrWhiteSpace($procBase)) { return $procBase }
    return "https://openrouter.ai/api/v1"
}

$apiKey = Get-OpenRouterApiKey
$baseUrl = Get-OpenRouterBaseUrl

$placeholder = "YOUR_OPENROUTER_KEY_HERE"

Write-Host ""
Write-Host "  === OpenRouter (terminal check) ===" -ForegroundColor Cyan

if ([string]::IsNullOrWhiteSpace($apiKey) -or ($apiKey -eq $placeholder)) {
    Write-Host "  STATUS: No real API key yet (missing or still the .env.example placeholder)." -ForegroundColor Yellow
    Write-Host "  NEXT:    Enter a valid OpenRouter key in this terminal when prompted." -ForegroundColor Yellow
    Write-Host ""
    exit 10
}

$apiKeySource = Get-OpenRouterApiKeySource
$mask = if ($apiKey.Length -ge 12) { "$($apiKey.Substring(0, 6))...$($apiKey.Substring($apiKey.Length - 4))" } else { "(short)" }
Write-Host ("  USING:  key from {0}, length {1}, fingerprint {2}" -f $apiKeySource, $apiKey.Length, $mask) -ForegroundColor DarkGray

$authUri = ($baseUrl.TrimEnd("/") + "/auth/key")

try {
    $headers = @{
        Authorization = "Bearer $apiKey"
    }
    $result = Invoke-RestMethod -Uri $authUri -Headers $headers -Method Get -TimeoutSec 45
    Write-Host "  STATUS: Key accepted by OpenRouter (GET /v1/auth/key OK)." -ForegroundColor Green
    if ($null -ne $result.data) {
        $details = @()
        if ($null -ne $result.data.label) { $details += "label=$($result.data.label)" }
        if ($null -ne $result.data.is_free_tier) { $details += "free_tier=$($result.data.is_free_tier)" }
        if ($null -ne $result.data.usage) { $details += "usage=$($result.data.usage)" }
        if ($null -ne $result.data.limit) { $details += "limit=$($result.data.limit)" }
        if ($details.Count -gt 0) {
            Write-Host ("  INFO:   {0}" -f ($details -join ", ")) -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    exit 0
}
catch {
    $status = $null
    try {
        $resp = $_.Exception.Response
        if ($null -ne $resp) { $status = [int]$resp.StatusCode }
    } catch { }

    if ($status -eq 401 -or $status -eq 403) {
        Write-Host "  STATUS: OpenRouter rejected this key (HTTP $status). It is set but not valid." -ForegroundColor Red
        Write-Host "  FIX:    Enter a valid OpenRouter key in this terminal when prompted." -ForegroundColor Red
        Write-Host ""
        exit 2
    }

    if ($status -eq 402) {
        Write-Host "  STATUS: Key is accepted by OpenRouter, but the account reports insufficient credits (HTTP 402)." -ForegroundColor Yellow
        Write-Host "  NEXT:   Add credits on OpenRouter if chat requests fail; you can continue launching Claw." -ForegroundColor Yellow
        Write-Host ""
        exit 0
    }

    Write-Host "  STATUS: OpenRouter did not return a usable response for this key (network or HTTP error)." -ForegroundColor DarkYellow
    Write-Host "  INFO:   $($_.Exception.Message)" -ForegroundColor DarkGray
    Write-Host "  NEXT:   Check internet / VPN / firewall / proxy if this repeats." -ForegroundColor DarkYellow
    Write-Host ""
    exit 3
}
