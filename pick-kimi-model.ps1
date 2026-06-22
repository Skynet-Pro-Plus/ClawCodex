#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive Kimi model picker for ClawCodex launch.

.DESCRIPTION
  Fetches models from GET https://api.moonshot.ai/v1/models using the saved API key,
  prefers current Kimi models, and prompts for a selection.
  Writes only the chosen id to stdout for launch-claw.ps1.
#>
param(
    [string]$ApiKey,
    [string]$DefaultModel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnvPath = Join-Path $RepoRoot ".env"
$DefaultKimiBase = "https://api.moonshot.ai/v1"
$FallbackDefaultModel = "kimi-k2.7-code"
$SecondaryDefaultModel = "kimi-k2.7-code-highspeed"
$TertiaryDefaultModel = "kimi-k2.6"
$QuaternaryDefaultModel = "kimi-k2.5"
$DeprecatedPrefixes = @("kimi-k2-", "kimi-thinking-preview", "kimi-latest")
$PreferredOrder = @($FallbackDefaultModel, $SecondaryDefaultModel, $TertiaryDefaultModel, $QuaternaryDefaultModel)

function Enable-ModernTls {
    try {
        $tls12 = [Net.SecurityProtocolType]::Tls12
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor $tls12
    } catch { }
}

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
        ($Value -eq "YOUR_KIMI_KEY_HERE") -or
        ($Value -eq "YOUR_MOONSHOT_KEY_HERE") -or
        ($Value -eq "YOUR_OPENROUTER_KEY_HERE")
}

function Is-DeprecatedModelId {
    param([string]$ModelId)
    if ([string]::IsNullOrWhiteSpace($ModelId)) { return $false }
    if ($ModelId -eq "kimi-latest" -or $ModelId -eq "kimi-thinking-preview") { return $true }
    if ($ModelId.StartsWith("kimi-k2-", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $ModelId.StartsWith("kimi-k2.5", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $ModelId.StartsWith("kimi-k2.6", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $ModelId.StartsWith("kimi-k2.7", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $false
}

function Get-KimiApiKey {
    if (-not (Is-PlaceholderKey $ApiKey)) { return $ApiKey.Trim() }

    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("KIMI_API_KEY") -and -not (Is-PlaceholderKey $dotenv["KIMI_API_KEY"])) {
        return $dotenv["KIMI_API_KEY"].Trim()
    }
    if ($dotenv.ContainsKey("MOONSHOT_API_KEY") -and -not (Is-PlaceholderKey $dotenv["MOONSHOT_API_KEY"])) {
        return $dotenv["MOONSHOT_API_KEY"].Trim()
    }
    if ($dotenv.ContainsKey("OPENAI_API_KEY") -and -not (Is-PlaceholderKey $dotenv["OPENAI_API_KEY"])) {
        $base = $dotenv["OPENAI_BASE_URL"]
        if ($base -and $base.ToLowerInvariant().Contains("api.moonshot.ai")) {
            return $dotenv["OPENAI_API_KEY"].Trim()
        }
    }

    $proc = [Environment]::GetEnvironmentVariable("KIMI_API_KEY", "Process")
    if (-not (Is-PlaceholderKey $proc)) { return $proc.Trim() }
    $procMoonshot = [Environment]::GetEnvironmentVariable("MOONSHOT_API_KEY", "Process")
    if (-not (Is-PlaceholderKey $procMoonshot)) { return $procMoonshot.Trim() }

    throw "Kimi API key is missing. Run set-kimi-key.ps1 or START-CLAW.bat first."
}

function Get-KimiBaseUrl {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("KIMI_BASE_URL") -and -not [string]::IsNullOrWhiteSpace($dotenv["KIMI_BASE_URL"])) {
        return $dotenv["KIMI_BASE_URL"].Trim()
    }
    $proc = [Environment]::GetEnvironmentVariable("KIMI_BASE_URL", "Process")
    if (-not [string]::IsNullOrWhiteSpace($proc)) { return $proc.Trim() }
    return $DefaultKimiBase
}

function Get-KimiModels {
    param(
        [string]$BaseUrl,
        [string]$Key
    )

    $uri = ($BaseUrl.TrimEnd("/") + "/models")
    $headers = @{ Authorization = "Bearer $Key" }
    $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 60

    if ($null -eq $response.data -or $response.data.Count -eq 0) {
        throw "Kimi returned no models for this API key."
    }

    $rows = @()
    foreach ($model in $response.data) {
        $id = [string]$model.id
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        $rows += [pscustomobject]@{
            Id               = $id
            ContextLength    = $model.context_length
            SupportsImageIn  = $model.supports_image_in
            SupportsVideoIn  = $model.supports_video_in
            SupportsReasoning = $model.supports_reasoning
            IsDeprecated     = (Is-DeprecatedModelId -ModelId $id)
        }
    }
    return @($rows | Sort-Object Id)
}

function Resolve-PreferredList {
    param([array]$AllModels)

    $current = @($AllModels | Where-Object {
        $_.Id.StartsWith("kimi-", [System.StringComparison]::OrdinalIgnoreCase) -and -not $_.IsDeprecated
    })

    if ($current.Count -eq 0) { return $AllModels }

    $ranked = @()
    foreach ($preferredId in $PreferredOrder) {
        $match = $current | Where-Object { $_.Id -eq $preferredId } | Select-Object -First 1
        if ($null -ne $match) { $ranked += $match }
    }
    $remaining = @($current | Where-Object { $PreferredOrder -notcontains $_.Id } | Sort-Object Id)
    return @($ranked + $remaining)
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

    foreach ($preferredId in $PreferredOrder) {
        $match = $Models | Where-Object { $_.Id -eq $preferredId } | Select-Object -First 1
        if ($null -ne $match) { return $match.Id }
    }

    return $Models[0].Id
}

$key = Get-KimiApiKey
$base = Get-KimiBaseUrl
Enable-ModernTls
Write-Host ""
Write-Host "  Fetching Kimi models (timeout 60s)..." -ForegroundColor Cyan

try {
    $allModels = Get-KimiModels -BaseUrl $base -Key $key
} catch {
    Write-Host ""
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$models = Resolve-PreferredList -AllModels $allModels

if ([string]::IsNullOrWhiteSpace($DefaultModel)) {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("CLAW_KIMI_MODEL")) {
        $DefaultModel = $dotenv["CLAW_KIMI_MODEL"]
    }
}

$defaultId = Resolve-DefaultModelId -Models $models -Preferred $DefaultModel

Write-Host ""
Write-Host "  Kimi models available from GET /models." -ForegroundColor Cyan
Write-Host "  Press Enter for the default, type a number to choose, or paste an exact model id."
Write-Host ""

for ($i = 0; $i -lt $models.Count; $i++) {
    $m = $models[$i]
    $index = $i + 1
    $details = @()
    if ($m.ContextLength) { $details += ("ctx {0}" -f $m.ContextLength) }
    if ($null -ne $m.SupportsImageIn) { $details += ("image={0}" -f $m.SupportsImageIn) }
    if ($null -ne $m.SupportsVideoIn) { $details += ("video={0}" -f $m.SupportsVideoIn) }
    if ($null -ne $m.SupportsReasoning) { $details += ("reasoning={0}" -f $m.SupportsReasoning) }
    if ($m.IsDeprecated) { $details += "deprecated" }
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

    $exact = $allModels | Where-Object { $_.Id -eq $selection } | Select-Object -First 1
    if ($null -ne $exact) {
        Write-Output $exact.Id
        exit 0
    }

    Write-Host "  Model '$selection' was not in the Kimi model list." -ForegroundColor Yellow
}
