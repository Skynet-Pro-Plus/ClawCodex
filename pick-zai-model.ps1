#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive Z.ai model picker for ClawCodex launch.

.DESCRIPTION
  Fetches models from GET https://open.bigmodel.cn/api/paas/v4/models using the saved API key,
  filters to GLM ids (`glm-4*`, `glm-5*`), and prompts for a selection.
  Writes only the chosen id to stdout for launch-claw.ps1.
#>
param(
    [string]$ApiKey,
    [string]$DefaultModel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnvPath = Join-Path $RepoRoot ".env"
$DefaultZaiBase = "https://open.bigmodel.cn/api/paas/v4"
$FallbackDefaultModel = "glm-5.2"

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

function Is-PlaceholderKey {
    param([string]$Value)
    return [string]::IsNullOrWhiteSpace($Value) -or
        ($Value -eq "YOUR_ZAI_KEY_HERE") -or
        ($Value -eq "YOUR_OPENROUTER_KEY_HERE")
}

function Get-ZaiApiKey {
    if (-not (Is-PlaceholderKey $ApiKey)) { return $ApiKey.Trim() }

    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("ZAI_API_KEY") -and -not (Is-PlaceholderKey $dotenv["ZAI_API_KEY"])) {
        return $dotenv["ZAI_API_KEY"].Trim()
    }
    if ($dotenv.ContainsKey("OPENAI_API_KEY") -and -not (Is-PlaceholderKey $dotenv["OPENAI_API_KEY"])) {
        $base = $dotenv["OPENAI_BASE_URL"]
        if ($base -and $base.ToLowerInvariant().Contains("bigmodel.cn")) {
            return $dotenv["OPENAI_API_KEY"].Trim()
        }
    }

    $proc = [Environment]::GetEnvironmentVariable("ZAI_API_KEY", "Process")
    if (-not (Is-PlaceholderKey $proc)) { return $proc.Trim() }

    throw "Z.ai API key is missing. Run set-zai-key.ps1 or START-CLAW.bat first."
}

function Get-ZaiBaseUrl {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("ZAI_BASE_URL") -and -not [string]::IsNullOrWhiteSpace($dotenv["ZAI_BASE_URL"])) {
        return $dotenv["ZAI_BASE_URL"].Trim()
    }
    $proc = [Environment]::GetEnvironmentVariable("ZAI_BASE_URL", "Process")
    if (-not [string]::IsNullOrWhiteSpace($proc)) { return $proc.Trim() }
    return $DefaultZaiBase
}

function Get-ZaiModels {
    param(
        [string]$BaseUrl,
        [string]$Key
    )

    $uri = ($BaseUrl.TrimEnd("/") + "/models")
    $headers = @{ Authorization = "Bearer $Key" }
    $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 60

    if ($null -eq $response.data -or $response.data.Count -eq 0) {
        throw "Z.ai returned no models for this API key."
    }

    $allRows = @()
    foreach ($model in $response.data) {
        $id = [string]$model.id
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        $allRows += [pscustomobject]@{
            Id      = $id
            OwnedBy = if ($model.owned_by) { [string]$model.owned_by } else { "Z.ai" }
            Created = $model.created
            Object  = $model.object
        }
    }
    return @($allRows | Sort-Object Id)
}

function Filter-ToolCapableGlmModels {
    param([array]$Models)
    return @($Models | Where-Object {
        $_.Id.StartsWith("glm-4", [System.StringComparison]::OrdinalIgnoreCase) -or
        $_.Id.StartsWith("glm-5", [System.StringComparison]::OrdinalIgnoreCase)
    })
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

    $fallback = $Models | Where-Object { $_.Id -eq $FallbackDefaultModel } | Select-Object -First 1
    if ($null -ne $fallback) { return $fallback.Id }

    return $Models[0].Id
}

$key = Get-ZaiApiKey
$base = Get-ZaiBaseUrl
Write-Host ""
Write-Host "  Fetching Z.ai models (timeout 60s)..." -ForegroundColor Cyan

try {
    $allModels = Get-ZaiModels -BaseUrl $base -Key $key
} catch {
    Write-Host ""
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$models = Filter-ToolCapableGlmModels -Models $allModels
if ($models.Count -eq 0) {
    Write-Host ""
    Write-Host "  ERROR: No GLM models matched prefix filter (glm-4* / glm-5*)." -ForegroundColor Red
    Write-Host "  INFO:  Z.ai returned $($allModels.Count) total model(s)." -ForegroundColor DarkGray
    exit 1
}

if ([string]::IsNullOrWhiteSpace($DefaultModel)) {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("CLAW_ZAI_MODEL")) {
        $DefaultModel = $dotenv["CLAW_ZAI_MODEL"]
    }
}

$defaultId = Resolve-DefaultModelId -Models $models -Preferred $DefaultModel

Write-Host ""
Write-Host "  Z.ai GLM models (filtered by id prefix: glm-4* / glm-5*)." -ForegroundColor Cyan
Write-Host "  Press Enter for the default, type a number to choose, or paste an exact model id."
Write-Host ""

for ($i = 0; $i -lt $models.Count; $i++) {
    $m = $models[$i]
    $index = $i + 1
    Write-Host ("  [{0}] {1}" -f $index, $m.Id)
}

Write-Host ""
while ($true) {
    $prompt = "  Model selection [$defaultId]: "
    $selection = Read-Host $prompt
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

    $exact = $allModels | Where-Object { $_.Id -eq $selection } | Select-Object -First 1
    if ($null -ne $exact) {
        Write-Output $exact.Id
        exit 0
    }

    Write-Host "  Model '$selection' was not in the Z.ai model list." -ForegroundColor Yellow
}
