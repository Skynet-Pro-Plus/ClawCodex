#Requires -Version 5.1
<#
.SYNOPSIS
  Terminal-friendly Cerebras API key check for ClawCodex onboarding.

.DESCRIPTION
  - If no key or placeholder: prints status and exits 10.
  - If a key is set: GET https://api.cerebras.ai/v1/models with Bearer auth.
    - 200: key accepted, exit 0
    - 401/403: key rejected, exit 2
    - Other/network: warning, exit 3

  Credential resolution: repo-root .env wins over process environment.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnv = Join-Path $RepoRoot ".env"
$CerebrasBase = "https://api.cerebras.ai/v1"

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
    return [string]::IsNullOrWhiteSpace($Value) -or
        ($Value -eq "YOUR_CEREBRAS_KEY_HERE") -or
        ($Value -eq "YOUR_OPENROUTER_KEY_HERE")
}

function Get-CerebrasApiKey {
    $fileKey = $null
    if ($fileVars.ContainsKey("CEREBRAS_API_KEY")) {
        $fileKey = $fileVars["CEREBRAS_API_KEY"].Trim()
    }
    $procKey = [Environment]::GetEnvironmentVariable("CEREBRAS_API_KEY", "Process")
    if ($null -ne $procKey) { $procKey = $procKey.Trim() }

    if (-not (Is-PlaceholderKey $fileKey)) {
        if ((-not (Is-PlaceholderKey $procKey)) -and ($fileKey -ne $procKey)) {
            Write-Host "  NOTE: CEREBRAS_API_KEY is set in both .env and this process; using .env for validation." -ForegroundColor DarkYellow
        }
        return $fileKey
    }
    if (-not (Is-PlaceholderKey $procKey)) { return $procKey }
    return $null
}

function Get-CerebrasApiKeySource {
    $fileKey = $null
    if ($fileVars.ContainsKey("CEREBRAS_API_KEY")) {
        $fileKey = $fileVars["CEREBRAS_API_KEY"].Trim()
    }
    if (-not (Is-PlaceholderKey $fileKey)) { return ".env" }
    return "process env"
}

$apiKey = Get-CerebrasApiKey

Write-Host ""
Write-Host "  === Cerebras (terminal check) ===" -ForegroundColor Cyan

if (Is-PlaceholderKey $apiKey) {
    Write-Host "  STATUS: No real Cerebras API key yet (missing or still a placeholder)." -ForegroundColor Yellow
    Write-Host "  NEXT:    Enter a valid Cerebras key in this terminal when prompted." -ForegroundColor Yellow
    Write-Host ""
    exit 10
}

$apiKeySource = Get-CerebrasApiKeySource
$mask = if ($apiKey.Length -ge 12) { "$($apiKey.Substring(0, 6))...$($apiKey.Substring($apiKey.Length - 4))" } else { "(short)" }
Write-Host ("  USING:  key from {0}, length {1}, fingerprint {2}" -f $apiKeySource, $apiKey.Length, $mask) -ForegroundColor DarkGray

$modelsUri = ($CerebrasBase.TrimEnd("/") + "/models")

try {
    $headers = @{
        Authorization = "Bearer $apiKey"
    }
    $result = Invoke-RestMethod -Uri $modelsUri -Headers $headers -Method Get -TimeoutSec 45
    Write-Host "  STATUS: Key accepted by Cerebras (GET /v1/models OK)." -ForegroundColor Green
    if ($null -ne $result.data -and $result.data.Count -gt 0) {
        $sample = @($result.data | Select-Object -First 3 | ForEach-Object { $_.id }) -join ", "
        Write-Host ("  INFO:   {0} model(s) available; examples: {1}" -f $result.data.Count, $sample) -ForegroundColor DarkGray
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
        Write-Host "  STATUS: Cerebras rejected this key (HTTP $status). It is set but not valid." -ForegroundColor Red
        Write-Host "  FIX:    Enter a valid Cerebras key in this terminal when prompted." -ForegroundColor Red
        Write-Host ""
        exit 2
    }

    Write-Host "  STATUS: Cerebras did not return a usable response for this key (network or HTTP error)." -ForegroundColor DarkYellow
    Write-Host "  INFO:   $($_.Exception.Message)" -ForegroundColor DarkGray
    Write-Host "  NEXT:   Check internet / VPN / firewall / proxy if this repeats." -ForegroundColor DarkYellow
    Write-Host ""
    exit 3
}
