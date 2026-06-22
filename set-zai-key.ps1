#Requires -Version 5.1
<#
.SYNOPSIS
  Set or replace ZAI_API_KEY in repo-root .env from the CLI (masked input).
#>
param(
    [switch]$NoVerify
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnv = Join-Path $RepoRoot ".env"
$Example = Join-Path $RepoRoot ".env.example"
$DefaultZaiBase = "https://open.bigmodel.cn/api/paas/v4"
$DefaultZaiModel = "glm-5.2"

function Ensure-DotEnvFromExample {
    if (Test-Path -LiteralPath $DotEnv) { return }
    if (-not (Test-Path -LiteralPath $Example)) {
        @(
            "# ClawCodex provider credentials (repo root).",
            "CLAW_PROVIDER=openrouter",
            "OPENAI_BASE_URL=https://openrouter.ai/api/v1",
            "OPENAI_API_KEY=YOUR_OPENROUTER_KEY_HERE",
            "CEREBRAS_API_KEY=YOUR_CEREBRAS_KEY_HERE",
            "CLAW_CEREBRAS_MODEL=gpt-oss-120b",
            "ZAI_BASE_URL=$DefaultZaiBase",
            "ZAI_API_KEY=YOUR_ZAI_KEY_HERE",
            "CLAW_ZAI_MODEL=$DefaultZaiModel"
        ) | Set-Content -LiteralPath $DotEnv -Encoding UTF8
        Write-Host "Created .env with default provider placeholders." -ForegroundColor Yellow
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
Write-Host "  === Set Z.ai API key (input hidden) ===" -ForegroundColor Cyan
Write-Host "  Paste your key and press Enter. Leave empty to cancel." -ForegroundColor Gray
Write-Host ""
$secure = Read-Host -AsSecureString
if ($null -eq $secure -or $secure.Length -eq 0) {
    Write-Host "  Cancelled - no changes." -ForegroundColor Yellow
    exit 1
}

$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($bstr).Trim()
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$plain = -join ($plain.ToCharArray() | Where-Object { [int]$_ -ge 0x20 -and [int]$_ -lt 0x7F })
if ([string]::IsNullOrWhiteSpace($plain)) {
    Write-Host "  Cancelled - empty key." -ForegroundColor Yellow
    exit 1
}

$lines = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $DotEnv -Encoding UTF8 | ForEach-Object { $lines.Add($_) }

$hadKey = [ref]$false
$hadBase = [ref]$false
$hadProvider = [ref]$false
$hadModel = [ref]$false
$hadOpenAiBase = [ref]$false
$hadOpenAiKey = [ref]$false

Set-DotEnvValue -Lines $lines -Name "ZAI_API_KEY" -Value $plain -Found $hadKey
Set-DotEnvValue -Lines $lines -Name "ZAI_BASE_URL" -Value $DefaultZaiBase -Found $hadBase
Set-DotEnvValue -Lines $lines -Name "CLAW_PROVIDER" -Value "zai" -Found $hadProvider
Set-DotEnvValue -Lines $lines -Name "CLAW_ZAI_MODEL" -Value $DefaultZaiModel -Found $hadModel
Set-DotEnvValue -Lines $lines -Name "OPENAI_BASE_URL" -Value $DefaultZaiBase -Found $hadOpenAiBase
Set-DotEnvValue -Lines $lines -Name "OPENAI_API_KEY" -Value $plain -Found $hadOpenAiKey

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($DotEnv, $lines.ToArray(), $utf8NoBom)
Protect-LocalCredentialFile -Path $DotEnv

$verify = (Get-Content -LiteralPath $DotEnv -Encoding UTF8 |
    Where-Object { $_ -match '^\s*ZAI_API_KEY\s*=' } |
    Select-Object -First 1)
$verifyVal = if ($verify) { ($verify -replace '^\s*ZAI_API_KEY\s*=\s*', '').Trim() } else { '' }
if ($verifyVal -ne $plain -or [string]::IsNullOrWhiteSpace($verifyVal)) {
    Write-Host ""
    Write-Host "  ERROR: .env round-trip check failed (saved value did not match)." -ForegroundColor Red
    Write-Host "  Path:   $DotEnv" -ForegroundColor Red
    Write-Host "  Hint:   close any other process holding .env (OneDrive sync, editor) and retry." -ForegroundColor Red
    exit 4
}

$mask = if ($plain.Length -ge 12) { "$($plain.Substring(0, 6))...$($plain.Substring($plain.Length - 4))" } else { "(short)" }
Write-Host ""
Write-Host ("  Saved ZAI_API_KEY to {0} (length {1}, fingerprint {2})" -f $DotEnv, $plain.Length, $mask) -ForegroundColor Green

if (-not $NoVerify) {
    Write-Host ""
    & (Join-Path $RepoRoot "validate-zai.ps1")
    $v = $LASTEXITCODE
    if ($v -eq 2) {
        Write-Host "  Z.ai still rejected this key. Try again." -ForegroundColor Red
        exit 2
    }
    if ($v -ne 0 -and $v -ne 3) {
        Write-Host "  Z.ai did not validate this key yet (validator exit $v)." -ForegroundColor Yellow
        exit $v
    }
}

Write-Host ""
exit 0
