#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive LM Studio model picker for ClawCodex local launch.

.DESCRIPTION
  Fetches models from GET {LMSTUDIO_BASE_URL}/models and prompts for a selection.
  Writes the chosen id to stdout for set-lmstudio-settings.ps1 / launch-claw.ps1.
#>
param(
    [string]$BaseUrl,
    [string]$ApiKey,
    [string]$DefaultModel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnvPath = Join-Path $RepoRoot ".env"
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

function Get-LmStudioBaseUrl {
    if (-not (Is-PlaceholderValue $BaseUrl)) { return $BaseUrl.Trim().TrimEnd("/") }
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("LMSTUDIO_BASE_URL") -and -not (Is-PlaceholderValue $dotenv["LMSTUDIO_BASE_URL"])) {
        return $dotenv["LMSTUDIO_BASE_URL"].Trim().TrimEnd("/")
    }
    return $DefaultBase
}

function Get-LmStudioApiKey {
    if (-not (Is-PlaceholderValue $ApiKey)) { return $ApiKey.Trim() }
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("LMSTUDIO_API_KEY") -and -not (Is-PlaceholderValue $dotenv["LMSTUDIO_API_KEY"])) {
        return $dotenv["LMSTUDIO_API_KEY"].Trim()
    }
    return "lm-studio"
}

function Get-LmStudioModels {
    param(
        [string]$Base,
        [string]$Key
    )

    $uri = ($Base + "/models")
    $headers = @{ Authorization = "Bearer $Key" }
    $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 30

    if ($null -eq $response.data -or $response.data.Count -eq 0) {
        throw "LM Studio returned no models. Load a model in LM Studio and try again."
    }

    $rows = @()
    foreach ($model in $response.data) {
        $id = [string]$model.id
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        $rows += [pscustomobject]@{
            Id = $id
        }
    }

    if ($rows.Count -eq 0) {
        throw "LM Studio returned no usable model ids."
    }

    return @($rows | Sort-Object Id)
}

function Resolve-DefaultModelId {
    param(
        [array]$Models,
        [string]$Preferred
    )

    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        $match = $Models | Where-Object { $_.Id -eq $Preferred.Trim() } | Select-Object -First 1
        if ($null -ne $match) { return $match.Id }
    }

    return $Models[0].Id
}

$base = Get-LmStudioBaseUrl
$key = Get-LmStudioApiKey

Write-Host ""
Write-Host "  Fetching LM Studio models from $base ..." -ForegroundColor Cyan

try {
    $models = Get-LmStudioModels -Base $base -Key $key
} catch {
    Write-Host ""
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($DefaultModel)) {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("CLAW_LOCAL_MODEL")) {
        $DefaultModel = $dotenv["CLAW_LOCAL_MODEL"]
    }
}

$defaultId = Resolve-DefaultModelId -Models $models -Preferred $DefaultModel

Write-Host ""
Write-Host "  Models reported by LM Studio (GET /models)." -ForegroundColor Cyan
Write-Host "  Press Enter for the default, type a number, or paste an exact model id."
Write-Host ""

for ($i = 0; $i -lt $models.Count; $i++) {
    $index = $i + 1
    Write-Host ("  [{0}] {1}" -f $index, $models[$i].Id)
}

Write-Host ""

while ($true) {
    $selection = Read-Host "  Model selection [$defaultId]: "
    $selection = if ($null -eq $selection) { "" } else { $selection.Trim() }

    if ([string]::IsNullOrWhiteSpace($selection)) {
        Write-Output $defaultId
        exit 0
    }

    if ($selection -match '^\d+$') {
        $n = [int]$selection
        if ($n -ge 1 -and $n -le $models.Count) {
            Write-Output $models[$n - 1].Id
            exit 0
        }
        Write-Host "  Selection '$selection' is out of range." -ForegroundColor Yellow
        continue
    }

    $exact = $models | Where-Object { $_.Id -eq $selection } | Select-Object -First 1
    if ($null -ne $exact) {
        Write-Output $exact.Id
        exit 0
    }

    Write-Host "  Model '$selection' was not in the LM Studio model list." -ForegroundColor Yellow
}
