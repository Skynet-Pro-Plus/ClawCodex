#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive ClawCodex launcher: choose OpenRouter, Cerebras, Z.ai, DeepSeek, Kimi, or Local (LM Studio), validate settings, start claw REPL.

.DESCRIPTION
  1. Prompt for provider (OpenRouter, Cerebras, Z.ai, DeepSeek, Kimi, or Local/LM Studio).
  2. Look for the provider key in repo-root .env; prompt with hidden input if missing/invalid.
  3. OpenRouter + valid key: run claw doctor, then REPL with tool-capable model picker.
  4. Cerebras/Z.ai/DeepSeek/Kimi + valid key: pick a model from live provider models, then REPL with that model.
  5. Local/LM Studio: prompt for LM Studio settings when missing; reuse saved settings when available.
#>
param(
    [ValidateSet("openrouter", "cerebras", "zai", "deepseek", "kimi", "local")]
    [string]$Provider,
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnvPath = Join-Path $RepoRoot ".env"
$PackagedClawExe = Join-Path $RepoRoot "bin\windows\claw.exe"
$BuiltClawExe = Join-Path $env:LOCALAPPDATA "ClawCodex\cargo-target\release\claw.exe"
$ClawExe = if (Test-Path -LiteralPath $BuiltClawExe) { $BuiltClawExe } else { $PackagedClawExe }
$MaxKeyTries = 3

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

function Ensure-DotEnvExists {
    if (Test-Path -LiteralPath $DotEnvPath) { return }
    $example = Join-Path $RepoRoot ".env.example"
    if (Test-Path -LiteralPath $example) {
        Copy-Item -LiteralPath $example -Destination $DotEnvPath
        return
    }
    @(
        "CLAW_PROVIDER=openrouter",
        "OPENAI_BASE_URL=$OpenRouterBase",
        "OPENAI_API_KEY=YOUR_OPENROUTER_KEY_HERE",
        "CEREBRAS_API_KEY=YOUR_CEREBRAS_KEY_HERE",
        "CLAW_CEREBRAS_MODEL=$DefaultCerebrasModel",
        "ZAI_BASE_URL=$ZaiBase",
        "ZAI_API_KEY=YOUR_ZAI_KEY_HERE",
        "CLAW_ZAI_MODEL=$DefaultZaiModel",
        "DEEPSEEK_BASE_URL=$DeepSeekBase",
        "DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY_HERE",
        "CLAW_DEEPSEEK_MODEL=$DefaultDeepSeekModel",
        "KIMI_BASE_URL=$KimiBase",
        "KIMI_API_KEY=YOUR_KIMI_KEY_HERE",
        "MOONSHOT_API_KEY=YOUR_MOONSHOT_KEY_HERE",
        "CLAW_KIMI_MODEL=$DefaultKimiModel",
        "LMSTUDIO_BASE_URL=$DefaultLmStudioBase",
        "LMSTUDIO_API_KEY=$DefaultLmStudioApiKey",
        "CLAW_LOCAL_MODEL=YOUR_LOCAL_MODEL_HERE"
    ) | Set-Content -LiteralPath $DotEnvPath -Encoding UTF8
}

function Set-DotEnvLine {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [string]$Name,
        [string]$Value
    )
    $found = $false
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match "^\s*$([regex]::Escape($Name))\s*=") {
            $Lines[$i] = "$Name=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) {
        $Lines.Add("$Name=$Value")
    }
}

function Save-ProviderConfig {
    param(
        [string]$SelectedProvider,
        [string]$OpenRouterKey,
        [string]$CerebrasKey,
        [string]$CerebrasModel,
        [string]$ZaiKey,
        [string]$ZaiModel,
        [string]$DeepSeekKey,
        [string]$DeepSeekModel,
        [string]$KimiKey,
        [string]$KimiModel,
        [string]$LocalBaseUrl,
        [string]$LocalApiKey,
        [string]$LocalModel
    )

    Ensure-DotEnvExists
    $lines = [System.Collections.Generic.List[string]]::new()
    Get-Content -LiteralPath $DotEnvPath -Encoding UTF8 | ForEach-Object { $lines.Add($_) }

    Set-DotEnvLine -Lines $lines -Name "CLAW_PROVIDER" -Value $SelectedProvider

    if ($SelectedProvider -eq "cerebras") {
        if (-not (Is-PlaceholderKey $CerebrasKey)) {
            Set-DotEnvLine -Lines $lines -Name "CEREBRAS_API_KEY" -Value $CerebrasKey
            Set-DotEnvLine -Lines $lines -Name "OPENAI_BASE_URL" -Value $CerebrasBase
            Set-DotEnvLine -Lines $lines -Name "OPENAI_API_KEY" -Value $CerebrasKey
        }
        if (-not [string]::IsNullOrWhiteSpace($CerebrasModel)) {
            Set-DotEnvLine -Lines $lines -Name "CLAW_CEREBRAS_MODEL" -Value $CerebrasModel
        }
    } elseif ($SelectedProvider -eq "zai") {
        Set-DotEnvLine -Lines $lines -Name "ZAI_BASE_URL" -Value $ZaiBase
        if (-not (Is-PlaceholderKey $ZaiKey)) {
            Set-DotEnvLine -Lines $lines -Name "ZAI_API_KEY" -Value $ZaiKey
            Set-DotEnvLine -Lines $lines -Name "OPENAI_BASE_URL" -Value $ZaiBase
            Set-DotEnvLine -Lines $lines -Name "OPENAI_API_KEY" -Value $ZaiKey
        }
        if (-not [string]::IsNullOrWhiteSpace($ZaiModel)) {
            Set-DotEnvLine -Lines $lines -Name "CLAW_ZAI_MODEL" -Value $ZaiModel
        }
    } elseif ($SelectedProvider -eq "deepseek") {
        Set-DotEnvLine -Lines $lines -Name "DEEPSEEK_BASE_URL" -Value $DeepSeekBase
        if (-not (Is-PlaceholderKey $DeepSeekKey)) {
            Set-DotEnvLine -Lines $lines -Name "DEEPSEEK_API_KEY" -Value $DeepSeekKey
            Set-DotEnvLine -Lines $lines -Name "OPENAI_BASE_URL" -Value $DeepSeekBase
            Set-DotEnvLine -Lines $lines -Name "OPENAI_API_KEY" -Value $DeepSeekKey
        }
        if (-not [string]::IsNullOrWhiteSpace($DeepSeekModel)) {
            Set-DotEnvLine -Lines $lines -Name "CLAW_DEEPSEEK_MODEL" -Value $DeepSeekModel
        }
    } elseif ($SelectedProvider -eq "kimi") {
        Set-DotEnvLine -Lines $lines -Name "KIMI_BASE_URL" -Value $KimiBase
        if (-not (Is-PlaceholderKey $KimiKey)) {
            Set-DotEnvLine -Lines $lines -Name "KIMI_API_KEY" -Value $KimiKey
            Set-DotEnvLine -Lines $lines -Name "MOONSHOT_API_KEY" -Value $KimiKey
            Set-DotEnvLine -Lines $lines -Name "OPENAI_BASE_URL" -Value $KimiBase
            Set-DotEnvLine -Lines $lines -Name "OPENAI_API_KEY" -Value $KimiKey
        }
        if (-not [string]::IsNullOrWhiteSpace($KimiModel)) {
            Set-DotEnvLine -Lines $lines -Name "CLAW_KIMI_MODEL" -Value $KimiModel
        }
    } elseif ($SelectedProvider -eq "local") {
        if (-not [string]::IsNullOrWhiteSpace($LocalBaseUrl)) {
            Set-DotEnvLine -Lines $lines -Name "LMSTUDIO_BASE_URL" -Value $LocalBaseUrl
            Set-DotEnvLine -Lines $lines -Name "OPENAI_BASE_URL" -Value $LocalBaseUrl
        }
        if (-not [string]::IsNullOrWhiteSpace($LocalApiKey)) {
            Set-DotEnvLine -Lines $lines -Name "LMSTUDIO_API_KEY" -Value $LocalApiKey
            Set-DotEnvLine -Lines $lines -Name "OPENAI_API_KEY" -Value $LocalApiKey
        }
        if (-not [string]::IsNullOrWhiteSpace($LocalModel)) {
            Set-DotEnvLine -Lines $lines -Name "CLAW_LOCAL_MODEL" -Value $LocalModel
        }
    } else {
        if (-not (Is-PlaceholderKey $OpenRouterKey)) {
            Set-DotEnvLine -Lines $lines -Name "OPENAI_BASE_URL" -Value $OpenRouterBase
            Set-DotEnvLine -Lines $lines -Name "OPENAI_API_KEY" -Value $OpenRouterKey
        }
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($DotEnvPath, $lines.ToArray(), $utf8NoBom)
}

function Get-LocalBaseUrlFromDotEnv {
    param([hashtable]$DotEnv)
    $base = $DotEnv["LMSTUDIO_BASE_URL"]
    if (Is-PlaceholderKey $base) {
        $base = $DotEnv["OPENAI_BASE_URL"]
    }
    if (Is-PlaceholderKey $base) { return $null }
    return $base.Trim().TrimEnd("/")
}

function Get-LocalApiKeyFromDotEnv {
    param([hashtable]$DotEnv)
    $key = $DotEnv["LMSTUDIO_API_KEY"]
    if (Is-PlaceholderKey $key) {
        $key = $DotEnv["OPENAI_API_KEY"]
    }
    if (Is-PlaceholderKey $key) { return $DefaultLmStudioApiKey }
    return $key.Trim()
}

function Get-LocalModelFromDotEnv {
    param([hashtable]$DotEnv)
    $model = $DotEnv["CLAW_LOCAL_MODEL"]
    if (Is-PlaceholderKey $model) { return $null }
    return $model.Trim()
}

function Test-HasSavedLocalSettings {
    param([hashtable]$DotEnv)
    $base = Get-LocalBaseUrlFromDotEnv -DotEnv $DotEnv
    $model = Get-LocalModelFromDotEnv -DotEnv $DotEnv
    return (-not [string]::IsNullOrWhiteSpace($base)) -and (-not [string]::IsNullOrWhiteSpace($model))
}

function Select-Provider {
    $dotenv = Read-RepoDotEnv -Path $DotEnvPath
    $last = $dotenv["CLAW_PROVIDER"]
    if ($last -ne "cerebras" -and $last -ne "zai" -and $last -ne "deepseek" -and $last -ne "kimi" -and $last -ne "local") { $last = "openrouter" }
    $defaultChoice = switch ($last) {
        "cerebras" { "2" }
        "zai" { "3" }
        "deepseek" { "4" }
        "kimi" { "5" }
        "local" { "6" }
        default { "1" }
    }

    Write-Host ""
    Write-Host "  === Choose model provider ===" -ForegroundColor Cyan
    Write-Host "  [1] OpenRouter  (pick a tool-capable model after key check)"
    Write-Host "  [2] Cerebras    (pick a model from your account, then start the CLI)"
    Write-Host "  [3] Z.ai        (pick a GLM model from your account, then start the CLI)"
    Write-Host "  [4] DeepSeek    (pick a DeepSeek model from your account, then start the CLI)"
    Write-Host "  [5] Kimi        (pick a Kimi model from your account, then start the CLI)"
    Write-Host "  [6] Local       (LM Studio on this machine, then start the CLI)"
    Write-Host ""
    $choice = Read-Host "  Choice [$defaultChoice]"
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = $defaultChoice }

    switch ($choice.Trim()) {
        "2" { return "cerebras" }
        "cerebras" { return "cerebras" }
        "3" { return "zai" }
        "zai" { return "zai" }
        "4" { return "deepseek" }
        "deepseek" { return "deepseek" }
        "5" { return "kimi" }
        "kimi" { return "kimi" }
        "6" { return "local" }
        "local" { return "local" }
        default { return "openrouter" }
    }
}

function Test-ProviderKey {
    param([string]$SelectedProvider)

    if ($SelectedProvider -eq "cerebras") {
        & (Join-Path $RepoRoot "validate-cerebras.ps1")
    } elseif ($SelectedProvider -eq "zai") {
        & (Join-Path $RepoRoot "validate-zai.ps1")
    } elseif ($SelectedProvider -eq "deepseek") {
        & (Join-Path $RepoRoot "validate-deepseek.ps1")
    } elseif ($SelectedProvider -eq "kimi") {
        & (Join-Path $RepoRoot "validate-kimi.ps1")
    } elseif ($SelectedProvider -eq "local") {
        & (Join-Path $RepoRoot "validate-lmstudio.ps1")
    } else {
        & (Join-Path $RepoRoot "validate-openrouter.ps1")
    }
    return $LASTEXITCODE
}

function Invoke-ProviderKeyPrompt {
    param([string]$SelectedProvider)

    if ($SelectedProvider -eq "cerebras") {
        & (Join-Path $RepoRoot "set-cerebras-key.ps1")
    } elseif ($SelectedProvider -eq "zai") {
        & (Join-Path $RepoRoot "set-zai-key.ps1")
    } elseif ($SelectedProvider -eq "deepseek") {
        & (Join-Path $RepoRoot "set-deepseek-key.ps1")
    } elseif ($SelectedProvider -eq "kimi") {
        & (Join-Path $RepoRoot "set-kimi-key.ps1")
    } elseif ($SelectedProvider -eq "local") {
        & (Join-Path $RepoRoot "set-lmstudio-settings.ps1")
    } else {
        & (Join-Path $RepoRoot "set-openrouter-key.ps1")
    }
    return $LASTEXITCODE
}

function Ensure-ProviderCredentials {
    param([string]$SelectedProvider)

    for ($try = 1; $try -le $MaxKeyTries; $try++) {
        $code = Test-ProviderKey -SelectedProvider $SelectedProvider
        if ($code -eq 0) { return $true }
        if ($code -eq 3) {
            Write-Host ""
            Write-Host "  Continuing with a network warning so ClawCodex can show more diagnostics." -ForegroundColor Yellow
            return $true
        }

        if ($code -eq 10) {
            Write-Host ""
            Write-Host "  No valid $($SelectedProvider) key is saved yet." -ForegroundColor Yellow
        } elseif ($code -eq 2) {
            Write-Host ""
            Write-Host "  $($SelectedProvider) rejected your saved API key (HTTP 401/403)." -ForegroundColor Red
        } else {
            Write-Host ""
            Write-Host "  Unexpected validation exit code: $code" -ForegroundColor Yellow
        }

        if ($try -ge $MaxKeyTries) {
            Write-Host ""
            Write-Host "  Stopping after $MaxKeyTries key attempts." -ForegroundColor Red
            return $false
        }

        Write-Host ""
        Write-Host "  Key attempt $try of $MaxKeyTries. Enter or replace your API key now (input hidden)." -ForegroundColor Cyan
        Write-Host "  Press Enter on an empty line to cancel."
        Write-Host ""

        $setCode = Invoke-ProviderKeyPrompt -SelectedProvider $SelectedProvider
        if ($setCode -eq 1) {
            Write-Host ""
            Write-Host "  Key setup was cancelled." -ForegroundColor Yellow
            return $false
        }
        if ($setCode -eq 4) {
            Write-Host ""
            Write-Host "  The key was entered, but .env did not save it correctly." -ForegroundColor Red
            return $false
        }
    }

    return $false
}

function Ensure-LocalLmStudioSettings {
    for ($try = 1; $try -le $MaxKeyTries; $try++) {
        $dotenv = Read-RepoDotEnv -Path $DotEnvPath

        if (Test-HasSavedLocalSettings -DotEnv $dotenv) {
            $base = Get-LocalBaseUrlFromDotEnv -DotEnv $dotenv
            $model = Get-LocalModelFromDotEnv -DotEnv $dotenv
            Write-Host ""
            Write-Host "  Saved LM Studio settings:" -ForegroundColor DarkGray
            Write-Host ("    Base URL: {0}" -f $base) -ForegroundColor DarkGray
            Write-Host ("    Model:    {0}" -f $model) -ForegroundColor DarkGray
            Write-Host ""
            $useSaved = Read-Host "  Would you like to use saved settings? [Y/n]"
            if ($useSaved -notmatch '^[Nn]') {
                $code = Test-ProviderKey -SelectedProvider "local"
                if ($code -eq 0) { return $true }
                if ($code -eq 3) {
                    Write-Host ""
                    Write-Host "  Continuing with a network warning so ClawCodex can show more diagnostics." -ForegroundColor Yellow
                    return $true
                }
                Write-Host ""
                Write-Host "  Saved LM Studio settings did not connect." -ForegroundColor Yellow
            } else {
                Write-Host ""
                Write-Host "  Enter new LM Studio settings." -ForegroundColor Cyan
            }
        } else {
            Write-Host ""
            Write-Host "  No saved LM Studio settings yet." -ForegroundColor Yellow
        }

        if ($try -ge $MaxKeyTries) {
            Write-Host ""
            Write-Host "  Stopping after $MaxKeyTries LM Studio setup attempts." -ForegroundColor Red
            return $false
        }

        Write-Host ""
        $setCode = Invoke-ProviderKeyPrompt -SelectedProvider "local"
        if ($setCode -eq 1) {
            Write-Host ""
            Write-Host "  LM Studio setup was cancelled." -ForegroundColor Yellow
            return $false
        }
        if ($setCode -ne 0) {
            Write-Host ""
            Write-Host "  LM Studio settings were not saved correctly." -ForegroundColor Red
            continue
        }

        $code = Test-ProviderKey -SelectedProvider "local"
        if ($code -eq 0) { return $true }
        if ($code -eq 3) {
            Write-Host ""
            Write-Host "  Continuing with a network warning so ClawCodex can show more diagnostics." -ForegroundColor Yellow
            return $true
        }
    }

    return $false
}

function Apply-LaunchEnvironment {
    param(
        [string]$SelectedProvider,
        [hashtable]$DotEnv
    )

    # Clear inherited values so repo .env is authoritative for this launch.
    $env:OPENAI_API_KEY = $null
    $env:OPENAI_BASE_URL = $null
    $env:CEREBRAS_API_KEY = $null
    $env:ZAI_API_KEY = $null
    $env:DEEPSEEK_API_KEY = $null
    $env:KIMI_API_KEY = $null
    $env:MOONSHOT_API_KEY = $null

    if ($SelectedProvider -eq "cerebras") {
        $key = $DotEnv["CEREBRAS_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        $model = $DotEnv["CLAW_CEREBRAS_MODEL"]
        if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultCerebrasModel }

        $env:OPENAI_BASE_URL = $CerebrasBase
        $env:OPENAI_API_KEY = $key
        $env:CEREBRAS_API_KEY = $key
        $env:CLAW_PROVIDER = "cerebras"
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        # Suppress OpenRouter-first-run prompts when using Cerebras.
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"

        return @{
            ExplicitModel = $model
            ClawArgs        = @("--model", $model)
            SkipDoctor      = $true
        }
    }

    if ($SelectedProvider -eq "zai") {
        $base = $DotEnv["ZAI_BASE_URL"]
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $ZaiBase }
        $key = $DotEnv["ZAI_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        $model = $DotEnv["CLAW_ZAI_MODEL"]
        if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultZaiModel }

        $env:OPENAI_BASE_URL = $base
        $env:OPENAI_API_KEY = $key
        $env:ZAI_API_KEY = $key
        $env:CLAW_PROVIDER = "zai"
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        # Suppress OpenRouter-first-run prompts when using Z.ai.
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"

        return @{
            ExplicitModel = $model
            ClawArgs        = @("--model", $model)
            SkipDoctor      = $true
        }
    }

    if ($SelectedProvider -eq "deepseek") {
        $base = $DotEnv["DEEPSEEK_BASE_URL"]
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $DeepSeekBase }
        $key = $DotEnv["DEEPSEEK_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        $model = $DotEnv["CLAW_DEEPSEEK_MODEL"]
        if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultDeepSeekModel }

        $env:OPENAI_BASE_URL = $base
        $env:OPENAI_API_KEY = $key
        $env:DEEPSEEK_API_KEY = $key
        $env:CLAW_PROVIDER = "deepseek"
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        # Suppress OpenRouter-first-run prompts when using DeepSeek.
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"

        return @{
            ExplicitModel = $model
            ClawArgs        = @("--model", $model)
            SkipDoctor      = $true
        }
    }

    if ($SelectedProvider -eq "kimi") {
        $base = $DotEnv["KIMI_BASE_URL"]
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $KimiBase }
        $key = $DotEnv["KIMI_API_KEY"]
        if (Is-PlaceholderKey $key) { $key = $DotEnv["MOONSHOT_API_KEY"] }
        if (Is-PlaceholderKey $key) { $key = $DotEnv["OPENAI_API_KEY"] }
        $model = $DotEnv["CLAW_KIMI_MODEL"]
        if ([string]::IsNullOrWhiteSpace($model)) { $model = $DefaultKimiModel }

        $env:OPENAI_BASE_URL = $base
        $env:OPENAI_API_KEY = $key
        $env:KIMI_API_KEY = $key
        $env:MOONSHOT_API_KEY = $key
        $env:CLAW_PROVIDER = "kimi"
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        # Suppress OpenRouter-first-run prompts when using Kimi.
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"

        return @{
            ExplicitModel = $model
            ClawArgs        = @("--model", $model)
            SkipDoctor      = $true
        }
    }

    if ($SelectedProvider -eq "local") {
        $base = Get-LocalBaseUrlFromDotEnv -DotEnv $DotEnv
        if ([string]::IsNullOrWhiteSpace($base)) { $base = $DefaultLmStudioBase }
        $key = Get-LocalApiKeyFromDotEnv -DotEnv $DotEnv
        $model = Get-LocalModelFromDotEnv -DotEnv $DotEnv
        if ([string]::IsNullOrWhiteSpace($model)) { $model = "local-model" }

        $env:OPENAI_BASE_URL = $base
        $env:OPENAI_API_KEY = $key
        $env:LMSTUDIO_BASE_URL = $base
        $env:LMSTUDIO_API_KEY = $key
        $env:CLAW_PROVIDER = "local"
        $env:CLAW_SKIP_OPENROUTER_MODEL_PICKER = "1"
        $env:CLAW_NO_CREDENTIAL_PROMPT = "1"

        return @{
            ExplicitModel = $model
            ClawArgs        = @("--model", $model)
            SkipDoctor      = $true
        }
    }

    Remove-Item Env:CLAW_SKIP_OPENROUTER_MODEL_PICKER -ErrorAction SilentlyContinue
    Remove-Item Env:CLAW_NO_CREDENTIAL_PROMPT -ErrorAction SilentlyContinue
    $env:CLAW_PROVIDER = "openrouter"
    $key = $DotEnv["OPENAI_API_KEY"]
    $env:OPENAI_BASE_URL = $OpenRouterBase
    $env:OPENAI_API_KEY = $key

    return @{
        ExplicitModel = $null
        ClawArgs        = @()
    }
}

function Invoke-Claw {
    param([string[]]$ClawArgs)

    if (-not (Test-Path -LiteralPath $ClawExe)) {
        Write-Host ""
        Write-Host "  Missing: $ClawExe" -ForegroundColor Red
        Write-Host "  Build it first:  .\build-claw.ps1" -ForegroundColor Yellow
        return 1
    }

    Push-Location -LiteralPath $RepoRoot
    try {
        # Run in-process so stdin/stdout stay attached to this console.
        # Start-Process can detach input handles, which makes interactive
        # picker/REPL flows exit immediately.
        & $ClawExe @ClawArgs
    } finally {
        Pop-Location
    }
}

# --- main ---

if (-not (Test-Path -LiteralPath $ClawExe)) {
    Write-Host ""
    Write-Host "  Missing packaged CLI: $ClawExe" -ForegroundColor Red
    Write-Host "  From PowerShell in this repo folder, run:  .\build-claw.ps1" -ForegroundColor Yellow
    exit 1
}
Write-Host ("  Using CLI binary: {0}" -f $ClawExe) -ForegroundColor DarkGray

Ensure-DotEnvExists

if ([string]::IsNullOrWhiteSpace($Provider)) {
    $Provider = Select-Provider
} else {
    Write-Host ""
    Write-Host "  Using provider: $Provider" -ForegroundColor Cyan
}

if ($Provider -eq "local") {
    if (-not (Ensure-LocalLmStudioSettings)) {
        Write-Host ""
        Write-Host "  ClawCodex will not launch until LM Studio settings are saved." -ForegroundColor Yellow
        Write-Host "  Run START-CLAW.bat again when ready." -ForegroundColor Yellow
        exit 1
    }
} elseif (-not (Ensure-ProviderCredentials -SelectedProvider $Provider)) {
    Write-Host ""
    Write-Host "  ClawCodex will not launch until a valid key is saved." -ForegroundColor Yellow
    Write-Host "  Run START-CLAW.bat again when ready." -ForegroundColor Yellow
    exit 1
}

$dotenv = Read-RepoDotEnv -Path $DotEnvPath

$selectedCerebrasModel = $null
$selectedZaiModel = $null
$selectedDeepSeekModel = $null
$selectedKimiModel = $null
if ($Provider -eq "cerebras") {
    $preferred = if ($dotenv["CLAW_CEREBRAS_MODEL"]) { $dotenv["CLAW_CEREBRAS_MODEL"] } else { $DefaultCerebrasModel }
    try {
        $selectedCerebrasModel = & (Join-Path $RepoRoot "pick-cerebras-model.ps1") -DefaultModel $preferred
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($selectedCerebrasModel)) {
            Write-Host ""
            Write-Host "  Cerebras model selection failed." -ForegroundColor Red
            exit 1
        }
        $selectedCerebrasModel = $selectedCerebrasModel.Trim()
    } catch {
        Write-Host ""
        Write-Host "  Cerebras model selection failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
if ($Provider -eq "zai") {
    $preferred = if ($dotenv["CLAW_ZAI_MODEL"]) { $dotenv["CLAW_ZAI_MODEL"] } else { $DefaultZaiModel }
    try {
        $selectedZaiModel = & (Join-Path $RepoRoot "pick-zai-model.ps1") -DefaultModel $preferred
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($selectedZaiModel)) {
            Write-Host ""
            Write-Host "  Z.ai model selection failed." -ForegroundColor Red
            exit 1
        }
        $selectedZaiModel = $selectedZaiModel.Trim()
    } catch {
        Write-Host ""
        Write-Host "  Z.ai model selection failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
if ($Provider -eq "deepseek") {
    $preferred = if ($dotenv["CLAW_DEEPSEEK_MODEL"]) { $dotenv["CLAW_DEEPSEEK_MODEL"] } else { $DefaultDeepSeekModel }
    try {
        $selectedDeepSeekModel = & (Join-Path $RepoRoot "pick-deepseek-model.ps1") -DefaultModel $preferred
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($selectedDeepSeekModel)) {
            Write-Host ""
            Write-Host "  DeepSeek model selection failed." -ForegroundColor Red
            exit 1
        }
        $selectedDeepSeekModel = $selectedDeepSeekModel.Trim()
    } catch {
        Write-Host ""
        Write-Host "  DeepSeek model selection failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
if ($Provider -eq "kimi") {
    $preferred = if ($dotenv["CLAW_KIMI_MODEL"]) { $dotenv["CLAW_KIMI_MODEL"] } else { $DefaultKimiModel }
    try {
        $selectedKimiModel = & (Join-Path $RepoRoot "pick-kimi-model.ps1") -DefaultModel $preferred
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($selectedKimiModel)) {
            Write-Host ""
            Write-Host "  Kimi model selection failed." -ForegroundColor Red
            exit 1
        }
        $selectedKimiModel = $selectedKimiModel.Trim()
    } catch {
        Write-Host ""
        Write-Host "  Kimi model selection failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

Save-ProviderConfig `
    -SelectedProvider $Provider `
    -OpenRouterKey $dotenv["OPENAI_API_KEY"] `
    -CerebrasKey $dotenv["CEREBRAS_API_KEY"] `
    -CerebrasModel $(if ($selectedCerebrasModel) { $selectedCerebrasModel } elseif ($dotenv["CLAW_CEREBRAS_MODEL"]) { $dotenv["CLAW_CEREBRAS_MODEL"] } else { $DefaultCerebrasModel }) `
    -ZaiKey $dotenv["ZAI_API_KEY"] `
    -ZaiModel $(if ($selectedZaiModel) { $selectedZaiModel } elseif ($dotenv["CLAW_ZAI_MODEL"]) { $dotenv["CLAW_ZAI_MODEL"] } else { $DefaultZaiModel }) `
    -DeepSeekKey $dotenv["DEEPSEEK_API_KEY"] `
    -DeepSeekModel $(if ($selectedDeepSeekModel) { $selectedDeepSeekModel } elseif ($dotenv["CLAW_DEEPSEEK_MODEL"]) { $dotenv["CLAW_DEEPSEEK_MODEL"] } else { $DefaultDeepSeekModel }) `
    -KimiKey $(if ($dotenv["KIMI_API_KEY"]) { $dotenv["KIMI_API_KEY"] } elseif ($dotenv["MOONSHOT_API_KEY"]) { $dotenv["MOONSHOT_API_KEY"] } else { $null }) `
    -KimiModel $(if ($selectedKimiModel) { $selectedKimiModel } elseif ($dotenv["CLAW_KIMI_MODEL"]) { $dotenv["CLAW_KIMI_MODEL"] } else { $DefaultKimiModel }) `
    -LocalBaseUrl $(Get-LocalBaseUrlFromDotEnv -DotEnv $dotenv) `
    -LocalApiKey $(Get-LocalApiKeyFromDotEnv -DotEnv $dotenv) `
    -LocalModel $(Get-LocalModelFromDotEnv -DotEnv $dotenv)

$dotenv = Read-RepoDotEnv -Path $DotEnvPath
$launch = Apply-LaunchEnvironment -SelectedProvider $Provider -DotEnv $dotenv

Write-Host ""
if ($Provider -eq "openrouter") {
    Write-Host "  OpenRouter key OK. Next: pick a tool-capable model, then enter the ClawCodex REPL." -ForegroundColor Green
} elseif ($Provider -eq "local") {
    Write-Host "  LM Studio connected. Starting ClawCodex with model $($launch.ExplicitModel)." -ForegroundColor Green
    Write-Host "  (Using saved local LM Studio settings.)" -ForegroundColor DarkGray
} elseif ($Provider -eq "zai") {
    Write-Host "  Z.ai key OK. Starting ClawCodex with model $($launch.ExplicitModel)." -ForegroundColor Green
    Write-Host "  (Selected from live Z.ai /models list, filtered to GLM models.)" -ForegroundColor DarkGray
} elseif ($Provider -eq "deepseek") {
    Write-Host "  DeepSeek key OK. Starting ClawCodex with model $($launch.ExplicitModel)." -ForegroundColor Green
    Write-Host "  (Selected from live DeepSeek /models list.)" -ForegroundColor DarkGray
} elseif ($Provider -eq "kimi") {
    Write-Host "  Kimi key OK. Starting ClawCodex with model $($launch.ExplicitModel)." -ForegroundColor Green
    Write-Host "  (Selected from live Kimi /v1/models list.)" -ForegroundColor DarkGray
} else {
    Write-Host "  Cerebras key OK. Starting ClawCodex with model $($launch.ExplicitModel)." -ForegroundColor Green
    Write-Host "  (Selected from live Cerebras /v1/models list.)" -ForegroundColor DarkGray
}

if ($Provider -eq "cerebras" -or $Provider -eq "zai" -or $Provider -eq "deepseek" -or $Provider -eq "kimi" -or $Provider -eq "local") {
    Write-Host ""
    Write-Host "  Skipping ClawCodex doctor for non-OpenRouter launch - starting the REPL directly." -ForegroundColor DarkGray
} elseif (-not $SkipDoctor) {
    Write-Host ""
    Write-Host "  Running claw doctor..." -ForegroundColor Cyan
    Invoke-Claw -ClawArgs @("doctor")
    $doctorExit = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
    if ($doctorExit -ne 0) {
        Write-Host ""
        Write-Host "  claw doctor reported problems (exit $doctorExit)." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Starting ClawCodex..." -ForegroundColor Cyan
Write-Host "  Step 1/2: Initializing (you should see that line next)." -ForegroundColor Yellow
Write-Host "  Step 2/2: Banner and > prompt usually follow within 10-30 seconds." -ForegroundColor Yellow
Write-Host "  Do not close this window while loading." -ForegroundColor DarkGray
Write-Host ""
Invoke-Claw -ClawArgs $launch.ClawArgs
$replExit = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
if ($replExit -ne 0) {
    Write-Host ""
    Write-Host "  ClawCodex exited with code $replExit." -ForegroundColor Red
    Write-Host "  The window is being kept open so the error above can be inspected." -ForegroundColor Yellow
    [void](Read-Host "  Press Enter to close")
}
exit $replExit
