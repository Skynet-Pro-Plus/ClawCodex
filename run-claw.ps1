#Requires -Version 5.1
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClawArgs
)
<#
.SYNOPSIS
  Run the packaged ClawCodex `claw` CLI from this repo folder.

.DESCRIPTION
  Uses bin\windows\claw.exe. Pass any normal claw arguments after the script name,
  e.g.  .\run-claw.ps1 prompt "hello"   or   .\run-claw.ps1 --help

  Prefer run-claw.bat if you want Command Prompt without invoking PowerShell.

  Credentials: repo-root `.env` (copy from .env.example). Use START-CLAW.bat for
  the interactive OpenRouter/Cerebras/Z.ai/DeepSeek/Kimi picker and key prompts.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackagedClawExe = Join-Path $RepoRoot "bin\windows\claw.exe"
$BuiltClawExe = Join-Path $env:LOCALAPPDATA "ClawCodex\cargo-target\release\claw.exe"
$ClawExe = if (Test-Path -LiteralPath $BuiltClawExe) { $BuiltClawExe } else { $PackagedClawExe }
$OpenRouterBase = "https://openrouter.ai/api/v1"
$CerebrasBase = "https://api.cerebras.ai/v1"
$DefaultCerebrasModel = "gpt-oss-120b"
$ZaiBase = "https://open.bigmodel.cn/api/paas/v4"
$DefaultZaiModel = "glm-5.2"
$DeepSeekBase = "https://api.deepseek.com"
$DefaultDeepSeekModel = "deepseek-v4-flash"
$KimiBase = "https://api.moonshot.ai/v1"
$DefaultKimiModel = "kimi-k2.7-code"
$DefaultLmStudioBase = "http://127.0.0.1:1234/v1"
$DefaultLmStudioApiKey = "lm-studio"

function Read-RepoDotEnv {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { return }
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
        ($Value -eq "YOUR_OPENROUTER_KEY_HERE") -or
        ($Value -eq "YOUR_CEREBRAS_KEY_HERE") -or
        ($Value -eq "YOUR_ZAI_KEY_HERE") -or
        ($Value -eq "YOUR_DEEPSEEK_KEY_HERE") -or
        ($Value -eq "YOUR_KIMI_KEY_HERE") -or
        ($Value -eq "YOUR_MOONSHOT_KEY_HERE") -or
        ($Value -eq "YOUR_LMSTUDIO_BASE_URL_HERE") -or
        ($Value -eq "YOUR_LMSTUDIO_API_KEY_HERE") -or
        ($Value -eq "YOUR_LOCAL_MODEL_HERE")
}

function Test-ArgsIncludeModel {
    param([string[]]$ClawArgs)
    for ($i = 0; $i -lt $ClawArgs.Count; $i++) {
        if ($ClawArgs[$i] -eq "--model" -or $ClawArgs[$i] -eq "-m") { return $true }
        if ($ClawArgs[$i].StartsWith("--model=")) { return $true }
    }
    return $false
}

function Apply-ProviderFromDotEnv {
    param(
        [hashtable]$DotEnv,
        [string[]]$ClawArgs
    )

    $provider = $DotEnv["CLAW_PROVIDER"]
    if ([string]::IsNullOrWhiteSpace($provider)) { $provider = "openrouter" }
    $provider = $provider.Trim().ToLowerInvariant()

    if ($provider -eq "cerebras") {
        $key = $DotEnv["CEREBRAS_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        if (-not (Is-PlaceholderKey $key)) {
            $env:OPENAI_BASE_URL = $CerebrasBase
            $env:OPENAI_API_KEY = $key
            $env:CEREBRAS_API_KEY = $key
        }
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"
        $env:CLAW_PROVIDER = "cerebras"

        if (-not (Test-ArgsIncludeModel -ClawArgs $ClawArgs)) {
            $model = $DotEnv["CLAW_CEREBRAS_MODEL"]
            if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultCerebrasModel }
            return @("--model", $model) + $ClawArgs
        }
        return $ClawArgs
    }

    if ($provider -eq "zai") {
        $base = $DotEnv["ZAI_BASE_URL"]
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $ZaiBase }
        $key = $DotEnv["ZAI_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        if (-not (Is-PlaceholderKey $key)) {
            $env:OPENAI_BASE_URL = $base
            $env:OPENAI_API_KEY = $key
            $env:ZAI_API_KEY = $key
        }
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"
        $env:CLAW_PROVIDER = "zai"

        if (-not (Test-ArgsIncludeModel -ClawArgs $ClawArgs)) {
            $model = $DotEnv["CLAW_ZAI_MODEL"]
            if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultZaiModel }
            return @("--model", $model) + $ClawArgs
        }
        return $ClawArgs
    }

    if ($provider -eq "deepseek") {
        $base = $DotEnv["DEEPSEEK_BASE_URL"]
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $DeepSeekBase }
        $key = $DotEnv["DEEPSEEK_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        if (-not (Is-PlaceholderKey $key)) {
            $env:OPENAI_BASE_URL = $base
            $env:OPENAI_API_KEY = $key
            $env:DEEPSEEK_API_KEY = $key
        }
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"
        $env:CLAW_PROVIDER = "deepseek"

        if (-not (Test-ArgsIncludeModel -ClawArgs $ClawArgs)) {
            $model = $DotEnv["CLAW_DEEPSEEK_MODEL"]
            if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultDeepSeekModel }
            return @("--model", $model) + $ClawArgs
        }
        return $ClawArgs
    }

    if ($provider -eq "kimi") {
        $base = $DotEnv["KIMI_BASE_URL"]
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $KimiBase }
        $key = $DotEnv["KIMI_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["MOONSHOT_API_KEY"] }
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        if (-not (Is-PlaceholderKey $key)) {
            $env:OPENAI_BASE_URL = $base
            $env:OPENAI_API_KEY = $key
            $env:KIMI_API_KEY = $key
            $env:MOONSHOT_API_KEY = $key
        }
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"
        $env:CLAW_PROVIDER = "kimi"

        if (-not (Test-ArgsIncludeModel -ClawArgs $ClawArgs)) {
            $model = $DotEnv["CLAW_KIMI_MODEL"]
            if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultKimiModel }
            return @("--model", $model) + $ClawArgs
        }
        return $ClawArgs
    }

    if ($provider -eq "local") {
        $base = $DotEnv["LMSTUDIO_BASE_URL"]
        if (Is-PlaceholderKey $base) { $base = $DotEnv["OPENAI_BASE_URL"] }
        if (Is-PlaceholderKey $base) { $base = $DefaultLmStudioBase }
        $key = $DotEnv["LMSTUDIO_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        if (Is-PlaceholderKey $key) { $key = $DefaultLmStudioApiKey }
        $env:OPENAI_BASE_URL = $base
        $env:OPENAI_API_KEY = $key
        $env:LMSTUDIO_BASE_URL = $base
        $env:LMSTUDIO_API_KEY = $key
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"
        $env:CLAW_PROVIDER = "local"

        if (-not (Test-ArgsIncludeModel -ClawArgs $ClawArgs)) {
            $model = $DotEnv["CLAW_LOCAL_MODEL"]
            if (Is-PlaceholderKey $model) { $model = "local-model" }
            return @("--model", $model) + $ClawArgs
        }
        return $ClawArgs
    }

    Remove-Item Env:CLAW_SKIP_OPENROUTER_MODEL_PICKER -ErrorAction SilentlyContinue
    Remove-Item Env:CLAW_NO_CREDENTIAL_PROMPT -ErrorAction SilentlyContinue
    Remove-Item Env:ZAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:KIMI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue
    $key = $DotEnv["OPENAI_API_KEY"]
    if (-not (Is-PlaceholderKey $key)) {
        $env:OPENAI_BASE_URL = $OpenRouterBase
        $env:OPENAI_API_KEY = $key
    }
    return $ClawArgs
}

if (-not (Test-Path -LiteralPath $ClawExe)) {
    Write-Host "Missing: $ClawExe" -ForegroundColor Red
    Write-Host "Build it first:  .\build-claw.ps1" -ForegroundColor Yellow
    exit 1
}
Write-Host ("Using CLI binary: {0}" -f $ClawExe) -ForegroundColor DarkGray

$dotenvPath = Join-Path $RepoRoot ".env"
$dotenv = Read-RepoDotEnv -Path $dotenvPath
$provider = if ($dotenv.ContainsKey("CLAW_PROVIDER")) { $dotenv["CLAW_PROVIDER"].Trim().ToLowerInvariant() } else { "openrouter" }

$hasCreds = $false
if ($provider -eq "cerebras") {
    $cKey = $dotenv["CEREBRAS_API_KEY"]
    if (Is-PlaceholderKey $cKey) { $cKey = $dotenv["OPENAI_API_KEY"] }
    $hasCreds = -not (Is-PlaceholderKey $cKey)
} elseif ($provider -eq "zai") {
    $zKey = $dotenv["ZAI_API_KEY"]
    if (Is-PlaceholderKey $zKey) { $zKey = $dotenv["OPENAI_API_KEY"] }
    $hasCreds = -not (Is-PlaceholderKey $zKey)
} elseif ($provider -eq "deepseek") {
    $dKey = $dotenv["DEEPSEEK_API_KEY"]
    if (Is-PlaceholderKey $dKey) { $dKey = $dotenv["OPENAI_API_KEY"] }
    $hasCreds = -not (Is-PlaceholderKey $dKey)
} elseif ($provider -eq "kimi") {
    $kKey = $dotenv["KIMI_API_KEY"]
    if (Is-PlaceholderKey $kKey) { $kKey = $dotenv["MOONSHOT_API_KEY"] }
    if (Is-PlaceholderKey $kKey) { $kKey = $dotenv["OPENAI_API_KEY"] }
    $hasCreds = -not (Is-PlaceholderKey $kKey)
} elseif ($provider -eq "local") {
    $base = $dotenv["LMSTUDIO_BASE_URL"]
    if (Is-PlaceholderKey $base) { $base = $dotenv["OPENAI_BASE_URL"] }
    $model = $dotenv["CLAW_LOCAL_MODEL"]
    $hasCreds = (-not (Is-PlaceholderKey $base)) -and (-not (Is-PlaceholderKey $model))
} else {
    $hasCreds = -not (Is-PlaceholderKey $dotenv["OPENAI_API_KEY"])
}

if (-not $hasCreds) {
    Write-Host "No saved credentials for provider '$provider'." -ForegroundColor Yellow
    Write-Host "  Run START-CLAW.bat to choose OpenRouter, Cerebras, Z.ai, DeepSeek, Kimi, or Local (LM Studio) and enter settings." -ForegroundColor Yellow
    Write-Host ""
}

$resolvedClawArgs = Apply-ProviderFromDotEnv -DotEnv $dotenv -ClawArgs $ClawArgs

Push-Location -LiteralPath $RepoRoot
try {
    & $ClawExe @resolvedClawArgs
} finally {
    Pop-Location
}
