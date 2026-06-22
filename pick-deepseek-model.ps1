#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive DeepSeek model picker for ClawCodex launch.

.DESCRIPTION
  Fetches models from GET https://api.deepseek.com/models using the saved API key,
  prefers current DeepSeek models, and prompts for a selection.
  Writes only the chosen id to stdout for launch-claw.ps1.
#>
param(
    [string]$ApiKey,
    [string]$DefaultModel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnvPath = Join-Path $RepoRoot ".env"
$DefaultDeepSeekBase = "https://api.deepseek.com"
$FallbackDefaultModel = "deepseek-v4-flash"
$SecondaryDefaultModel = "deepseek-v4-pro"
$DeprecatedModelIds = @("deepseek-chat", "deepseek-reasoner")

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
        ($Value -eq "YOUR_DEEPSEEK_KEY_HERE") -or
        ($Value -eq "YOUR_OPENROUTER_KEY_HERE")
}

function Get-DeepSeekApiKey {
    if (-not (Is-PlaceholderKey $ApiKey)) { return $ApiKey.Trim() }

    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("DEEPSEEK_API_KEY") -and -not (Is-PlaceholderKey $dotenv["DEEPSEEK_API_KEY"])) {
        return $dotenv["DEEPSEEK_API_KEY"].Trim()
    }
    if ($dotenv.ContainsKey("OPENAI_API_KEY") -and -not (Is-PlaceholderKey $dotenv["OPENAI_API_KEY"])) {
        $base = $dotenv["OPENAI_BASE_URL"]
        if ($base -and $base.ToLowerInvariant().Contains("api.deepseek.com")) {
            return $dotenv["OPENAI_API_KEY"].Trim()
        }
    }

    $proc = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "Process")
    if (-not (Is-PlaceholderKey $proc)) { return $proc.Trim() }

    throw "DeepSeek API key is missing. Run set-deepseek-key.ps1 or START-CLAW.bat first."
}

function Get-DeepSeekBaseUrl {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("DEEPSEEK_BASE_URL") -and -not [string]::IsNullOrWhiteSpace($dotenv["DEEPSEEK_BASE_URL"])) {
        return $dotenv["DEEPSEEK_BASE_URL"].Trim()
    }
    $proc = [Environment]::GetEnvironmentVariable("DEEPSEEK_BASE_URL", "Process")
    if (-not [string]::IsNullOrWhiteSpace($proc)) { return $proc.Trim() }
    return $DefaultDeepSeekBase
}

function Get-DeepSeekModels {
    param(
        [string]$BaseUrl,
        [string]$Key
    )

    $uri = ($BaseUrl.TrimEnd("/") + "/models")
    $headers = @{ Authorization = "Bearer $Key" }
    $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 60

    if ($null -eq $response.data -or $response.data.Count -eq 0) {
        throw "DeepSeek returned no models for this API key."
    }

    $allRows = @()
    foreach ($model in $response.data) {
        $id = [string]$model.id
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        $allRows += [pscustomobject]@{
            Id          = $id
            IsDeprecated = ($DeprecatedModelIds -contains $id)
        }
    }
    return @($allRows | Sort-Object Id)
}

function Resolve-PreferredList {
    param([array]$AllModels)

    $primary = @($AllModels | Where-Object {
        $_.Id.StartsWith("deepseek-", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $_.IsDeprecated
    })

    if ($primary.Count -gt 0) { return $primary }
    return $AllModels
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

    $flash = $Models | Where-Object { $_.Id -eq $FallbackDefaultModel } | Select-Object -First 1
    if ($null -ne $flash) { return $flash.Id }

    $pro = $Models | Where-Object { $_.Id -eq $SecondaryDefaultModel } | Select-Object -First 1
    if ($null -ne $pro) { return $pro.Id }

    return $Models[0].Id
}

$key = Get-DeepSeekApiKey
$base = Get-DeepSeekBaseUrl
Enable-ModernTls
Write-Host ""
Write-Host "  Fetching DeepSeek models (timeout 60s)..." -ForegroundColor Cyan

try {
    $allModels = Get-DeepSeekModels -BaseUrl $base -Key $key
} catch {
    Write-Host ""
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$models = Resolve-PreferredList -AllModels $allModels

if ([string]::IsNullOrWhiteSpace($DefaultModel)) {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    if ($dotenv.ContainsKey("CLAW_DEEPSEEK_MODEL")) {
        $DefaultModel = $dotenv["CLAW_DEEPSEEK_MODEL"]
    }
}

$defaultId = Resolve-DefaultModelId -Models $models -Preferred $DefaultModel

Write-Host ""
Write-Host "  DeepSeek models available from GET /models." -ForegroundColor Cyan
if (@($allModels | Where-Object { $_.IsDeprecated }).Count -gt 0) {
    Write-Host "  Note: deprecated compatibility models are shown only as fallback." -ForegroundColor DarkGray
}
Write-Host "  Press Enter for the default, type a number to choose, or paste an exact model id."
Write-Host ""

for ($i = 0; $i -lt $models.Count; $i++) {
    $m = $models[$i]
    $index = $i + 1
    $suffix = if ($m.IsDeprecated) { " (deprecated)" } else { "" }
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

    Write-Host "  Model '$selection' was not in the DeepSeek model list." -ForegroundColor Yellow
}
