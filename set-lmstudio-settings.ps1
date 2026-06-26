#Requires -Version 5.1
<#
.SYNOPSIS
  Set or replace LM Studio local provider settings in repo-root .env.
#>
param(
    [switch]$NoVerify
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnv = Join-Path $RepoRoot ".env"
$Example = Join-Path $RepoRoot ".env.example"
$DefaultBase = "http://127.0.0.1:1234/v1"
$DefaultApiKey = "lm-studio"

function Ensure-DotEnvFromExample {
    if (Test-Path -LiteralPath $DotEnv) { return }
    if (-not (Test-Path -LiteralPath $Example)) {
        @(
            "# ClawCodex provider credentials (repo root).",
            "CLAW_PROVIDER=local",
            "LMSTUDIO_BASE_URL=$DefaultBase",
            "LMSTUDIO_API_KEY=$DefaultApiKey",
            "CLAW_LOCAL_MODEL=YOUR_LOCAL_MODEL_HERE"
        ) | Set-Content -LiteralPath $DotEnv -Encoding UTF8
        Write-Host "Created .env with default local provider placeholders." -ForegroundColor Yellow
        return
    }
    Copy-Item -LiteralPath $Example -Destination $DotEnv
    Write-Host "Created .env from .env.example." -ForegroundColor Yellow
}

function Protect-LocalCredentialFile {
    param([string]$Path)
    if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) { return }
    try {
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        $acl.SetAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($identity, "FullControl", "Allow"))
        $acl.SetAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new("SYSTEM", "FullControl", "Allow"))
        Set-Acl -LiteralPath $Path -AclObject $acl
    } catch {
        Write-Host "  NOTE:   Saved .env, but could not tighten file ACLs: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
}

function Set-DotEnvValue {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [string]$Name,
        [string]$Value,
        [ref]$Found
    )
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match "^\s*$([regex]::Escape($Name))\s*=") {
            $Lines[$i] = "$Name=$Value"
            $Found.Value = $true
            return
        }
    }
    $Lines.Add("$Name=$Value")
}

Ensure-DotEnvFromExample

Write-Host ""
Write-Host "  === LM Studio local settings ===" -ForegroundColor Cyan
Write-Host "  Start LM Studio and enable the local server before continuing." -ForegroundColor Gray
Write-Host ""

$baseInput = Read-Host "  LM Studio base URL [$DefaultBase]"
$base = if ([string]::IsNullOrWhiteSpace($baseInput)) { $DefaultBase } else { $baseInput.Trim().TrimEnd("/") }
if ($base -notmatch "/v1$") {
    if ($base.EndsWith("/")) {
        $base = ($base.TrimEnd("/") + "/v1")
    } else {
        $base = ($base + "/v1")
    }
}

$keyInput = Read-Host "  LM Studio API key [$DefaultApiKey]"
$key = if ([string]::IsNullOrWhiteSpace($keyInput)) { $DefaultApiKey } else { $keyInput.Trim() }

Write-Host ""
Write-Host "  Testing connection to $base ..." -ForegroundColor Cyan
try {
    $headers = @{ Authorization = "Bearer $key" }
    $null = Invoke-RestMethod -Uri ($base + "/models") -Headers $headers -Method Get -TimeoutSec 30
    Write-Host "  Connection OK." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "  ERROR: Could not reach LM Studio at $base" -ForegroundColor Red
    Write-Host "  INFO:  $($_.Exception.Message)" -ForegroundColor DarkGray
    Write-Host "  FIX:   Start LM Studio, load a model, enable the server, then try again." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host ""
try {
    $selectedModel = & (Join-Path $RepoRoot "pick-lmstudio-model.ps1") -BaseUrl $base -ApiKey $key
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($selectedModel)) {
        Write-Host "  LM Studio model selection failed." -ForegroundColor Red
        exit 1
    }
    $selectedModel = $selectedModel.Trim()
} catch {
    Write-Host "  LM Studio model selection failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$lines = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $DotEnv -Encoding UTF8 | ForEach-Object { $lines.Add($_) }

$hadBase = [ref]$false
$hadKey = [ref]$false
$hadModel = [ref]$false
$hadProvider = [ref]$false
$hadOpenAiBase = [ref]$false
$hadOpenAiKey = [ref]$false

Set-DotEnvValue -Lines $lines -Name "CLAW_PROVIDER" -Value "local" -Found $hadProvider
Set-DotEnvValue -Lines $lines -Name "LMSTUDIO_BASE_URL" -Value $base -Found $hadBase
Set-DotEnvValue -Lines $lines -Name "LMSTUDIO_API_KEY" -Value $key -Found $hadKey
Set-DotEnvValue -Lines $lines -Name "CLAW_LOCAL_MODEL" -Value $selectedModel -Found $hadModel
Set-DotEnvValue -Lines $lines -Name "OPENAI_BASE_URL" -Value $base -Found $hadOpenAiBase
Set-DotEnvValue -Lines $lines -Name "OPENAI_API_KEY" -Value $key -Found $hadOpenAiKey

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($DotEnv, $lines.ToArray(), $utf8NoBom)
Protect-LocalCredentialFile -Path $DotEnv

Write-Host ""
Write-Host "  Saved LM Studio settings to $DotEnv" -ForegroundColor Green
Write-Host ("  Base URL: {0}" -f $base) -ForegroundColor DarkGray
Write-Host ("  Model:    {0}" -f $selectedModel) -ForegroundColor DarkGray

if (-not $NoVerify) {
    Write-Host ""
    & (Join-Path $RepoRoot "validate-lmstudio.ps1")
    $v = $LASTEXITCODE
    if ($v -eq 2) {
        Write-Host "  LM Studio rejected these settings. Try again." -ForegroundColor Red
        exit 2
    }
    if ($v -ne 0 -and $v -ne 3) {
        Write-Host "  LM Studio did not validate yet (validator exit $v)." -ForegroundColor Yellow
        exit $v
    }
}

Write-Host ""
exit 0
