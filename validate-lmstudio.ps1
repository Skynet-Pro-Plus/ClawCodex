#Requires -Version 5.1
<#
.SYNOPSIS
  Terminal-friendly LM Studio connection check for ClawCodex local provider.

.DESCRIPTION
  - If base URL or model is missing: prints status and exits 10.
  - If configured: GET {base}/models with Bearer auth.
    - 200: connection OK, exit 0
    - 401/403: rejected, exit 2
    - Other/network: warning, exit 3

  Credential resolution: repo-root .env wins over process environment.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnv = Join-Path $RepoRoot ".env"
$DefaultBase = "http://127.0.0.1:1234/v1"

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

function Is-PlaceholderValue {
    param([string]$Value)
    return [string]::IsNullOrWhiteSpace($Value) -or
        ($Value -eq "YOUR_LMSTUDIO_BASE_URL_HERE") -or
        ($Value -eq "YOUR_LMSTUDIO_API_KEY_HERE") -or
        ($Value -eq "YOUR_LOCAL_MODEL_HERE")
}

function Get-LocalBaseUrl {
    param([hashtable]$Vars)
    $base = $null
    if ($Vars.ContainsKey("LMSTUDIO_BASE_URL")) { $base = $Vars["LMSTUDIO_BASE_URL"].Trim() }
    if (Is-PlaceholderValue $base) {
        $base = $Vars["OPENAI_BASE_URL"]
        if ($null -ne $base) { $base = $base.Trim() }
    }
    if (Is-PlaceholderValue $base) { return $null }
    return $base.TrimEnd("/")
}

function Get-LocalApiKey {
    param([hashtable]$Vars)
    $key = $null
    if ($Vars.ContainsKey("LMSTUDIO_API_KEY")) { $key = $Vars["LMSTUDIO_API_KEY"].Trim() }
    if (Is-PlaceholderValue $key) {
        $key = $Vars["OPENAI_API_KEY"]
        if ($null -ne $key) { $key = $key.Trim() }
    }
    if (Is-PlaceholderValue $key) { return "lm-studio" }
    return $key
}

function Get-LocalModel {
    param([hashtable]$Vars)
    $model = $null
    if ($Vars.ContainsKey("CLAW_LOCAL_MODEL")) { $model = $Vars["CLAW_LOCAL_MODEL"].Trim() }
    if (Is-PlaceholderValue $model) { return $null }
    return $model
}

$fileVars = Read-RepoDotEnv -Path $DotEnv
$baseUrl = Get-LocalBaseUrl -Vars $fileVars
$apiKey = Get-LocalApiKey -Vars $fileVars
$model = Get-LocalModel -Vars $fileVars

Write-Host ""
Write-Host "  === LM Studio (local check) ===" -ForegroundColor Cyan

if (Is-PlaceholderValue $baseUrl) {
    Write-Host "  STATUS: No LM Studio base URL saved yet." -ForegroundColor Yellow
    Write-Host "  NEXT:    Enter LM Studio settings when prompted." -ForegroundColor Yellow
    Write-Host ""
    exit 10
}

if (Is-PlaceholderValue $model) {
    Write-Host "  STATUS: LM Studio base URL is set, but no model is saved yet." -ForegroundColor Yellow
    Write-Host "  NEXT:    Choose a loaded model when prompted." -ForegroundColor Yellow
    Write-Host ""
    exit 10
}

Write-Host ("  USING:  base {0}" -f $baseUrl) -ForegroundColor DarkGray
Write-Host ("  USING:  model {0}" -f $model) -ForegroundColor DarkGray

$modelsUri = ($baseUrl + "/models")

try {
    $headers = @{ Authorization = "Bearer $apiKey" }
    $result = Invoke-RestMethod -Uri $modelsUri -Headers $headers -Method Get -TimeoutSec 30
    Write-Host "  STATUS: Connected to LM Studio (GET /models OK)." -ForegroundColor Green
    if ($null -ne $result.data -and $result.data.Count -gt 0) {
        $known = @($result.data | ForEach-Object { [string]$_.id })
        if ($known -contains $model) {
            Write-Host ("  INFO:   Saved model '{0}' is loaded in LM Studio." -f $model) -ForegroundColor DarkGray
        } else {
            Write-Host ("  WARN:   Saved model '{0}' was not in the current /models list." -f $model) -ForegroundColor DarkYellow
            Write-Host "  INFO:   LM Studio may still serve it, or you may need to reload the model." -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  WARN:   LM Studio returned no models. Load a model in LM Studio first." -ForegroundColor DarkYellow
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
        Write-Host "  STATUS: LM Studio rejected this API key (HTTP $status)." -ForegroundColor Red
        Write-Host "  FIX:    Re-enter LM Studio settings when prompted." -ForegroundColor Red
        Write-Host ""
        exit 2
    }

    Write-Host "  STATUS: Could not reach LM Studio (network or HTTP error)." -ForegroundColor DarkYellow
    Write-Host "  INFO:   $($_.Exception.Message)" -ForegroundColor DarkGray
    Write-Host "  NEXT:   Start LM Studio, enable the local server, and confirm the base URL." -ForegroundColor DarkYellow
    Write-Host ""
    exit 3
}
