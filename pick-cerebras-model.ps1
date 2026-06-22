#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive Cerebras model picker for ClawCodex launch.

.DESCRIPTION
  Fetches models from GET https://api.cerebras.ai/v1/models using the saved API key,
  lists only models returned by Cerebras for this account, and prompts for a selection.
  Writes the chosen id to stdout for launch-claw.ps1.
#>
param(
    [string]$ApiKey,
    [string]$DefaultModel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnvPath = Join-Path $RepoRoot ".env"
$CerebrasBase = "https://api.cerebras.ai/v1"
$FallbackDefaultModel = "gpt-oss-120b"

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
        ($Value -eq "YOUR_CEREBRAS_KEY_HERE") -or
        ($Value -eq "YOUR_OPENROUTER_KEY_HERE")
}

function Get-CerebrasApiKey {
    if (-not (Is-PlaceholderKey $ApiKey)) { return $ApiKey.Trim() }

    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("CEREBRAS_API_KEY") -and -not (Is-PlaceholderKey $dotenv["CEREBRAS_API_KEY"])) {
        return $dotenv["CEREBRAS_API_KEY"].Trim()
    }
    if ($dotenv.ContainsKey("OPENAI_API_KEY") -and -not (Is-PlaceholderKey $dotenv["OPENAI_API_KEY"])) {
        $base = $dotenv["OPENAI_BASE_URL"]
        if ($base -and $base.ToLowerInvariant().Contains("cerebras")) {
            return $dotenv["OPENAI_API_KEY"].Trim()
        }
    }

    $proc = [Environment]::GetEnvironmentVariable("CEREBRAS_API_KEY", "Process")
    if (-not (Is-PlaceholderKey $proc)) { return $proc.Trim() }

    throw "Cerebras API key is missing. Run set-cerebras-key.ps1 or START-CLAW.bat first."
}

function Get-PublicModelCatalog {
    try {
        $public = Invoke-RestMethod -Uri "https://api.cerebras.ai/public/v1/models" -Method Get -TimeoutSec 30
        $catalog = @{}
        if ($null -ne $public.data) {
            foreach ($entry in $public.data) {
                if ($entry.id) {
                    $catalog[$entry.id] = $entry
                }
            }
        }
        return $catalog
    } catch {
        return @{}
    }
}

function Get-CerebrasModels {
    param([string]$Key)

    $uri = ($CerebrasBase.TrimEnd("/") + "/models")
    $headers = @{ Authorization = "Bearer $Key" }
    $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 60

    if ($null -eq $response.data -or $response.data.Count -eq 0) {
        throw "Cerebras returned no models for this API key."
    }

    $catalog = Get-PublicModelCatalog
    $rows = @()

    foreach ($model in $response.data) {
        $id = [string]$model.id
        if ([string]::IsNullOrWhiteSpace($id)) { continue }

        $meta = $null
        if ($catalog.ContainsKey($id)) { $meta = $catalog[$id] }

        $displayName = $id
        if ($meta -and $meta.name) { $displayName = [string]$meta.name }

        $context = $null
        if ($meta -and $meta.context_length) { $context = [int]$meta.context_length }
        elseif ($meta -and $meta.max_context_length) { $context = [int]$meta.max_context_length }

        $tier = $null
        if ($meta -and $meta.metadata -and $meta.metadata.tier) { $tier = [string]$meta.metadata.tier }
        elseif ($meta -and $meta.tier) { $tier = [string]$meta.tier }

        $rows += [pscustomobject]@{
            Id          = $id
            DisplayName = $displayName
            OwnedBy     = if ($model.owned_by) { [string]$model.owned_by } else { "Cerebras" }
            Context     = $context
            Tier        = $tier
        }
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

    $fallback = $Models | Where-Object { $_.Id -eq $FallbackDefaultModel } | Select-Object -First 1
    if ($null -ne $fallback) { return $fallback.Id }

    return $Models[0].Id
}

$key = Get-CerebrasApiKey
Write-Host ""
Write-Host "  Fetching Cerebras models (timeout 60s)..." -ForegroundColor Cyan

try {
    $models = Get-CerebrasModels -Key $key
} catch {
    Write-Host ""
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($DefaultModel)) {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("CLAW_CEREBRAS_MODEL")) {
        $DefaultModel = $dotenv["CLAW_CEREBRAS_MODEL"]
    }
}

$defaultId = Resolve-DefaultModelId -Models $models -Preferred $DefaultModel

Write-Host ""
Write-Host "  Cerebras models available on your account (from GET /v1/models)." -ForegroundColor Cyan
Write-Host "  Press Enter for the default, type a number to choose, or paste an exact model id."
Write-Host ""

for ($i = 0; $i -lt $models.Count; $i++) {
    $m = $models[$i]
    $index = $i + 1
    $details = @()
    if ($m.DisplayName -ne $m.Id) { $details += $m.DisplayName }
    if ($m.Context) { $details += "ctx $($m.Context)" }
    if ($m.Tier) { $details += $m.Tier }
    $suffix = if ($details.Count -gt 0) { " (" + ($details -join " | ") + ")" } else { "" }
    Write-Host ("  [{0}] {1}{2}" -f $index, $m.Id, $suffix)
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

    $exact = $models | Where-Object { $_.Id -eq $selection } | Select-Object -First 1
    if ($null -ne $exact) {
        Write-Output $exact.Id
        exit 0
    }

    Write-Host "  Model '$selection' was not in the Cerebras model list." -ForegroundColor Yellow
}
