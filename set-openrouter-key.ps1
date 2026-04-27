#Requires -Version 5.1
<#
.SYNOPSIS
  Set or replace OPENAI_API_KEY in repo-root .env from the CLI (masked input).

.DESCRIPTION
  Prompts for the key with Read-Host -AsSecureString, updates or appends OPENAI_API_KEY=,
  ensures OPENAI_BASE_URL= exists (defaults to OpenRouter), preserves other lines and comments.
  Optionally runs validate-openrouter.ps1 when -Verify is set (default: true).
#>
param(
    [switch]$NoVerify
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DotEnv = Join-Path $RepoRoot ".env"
$Example = Join-Path $RepoRoot ".env.example"

function Ensure-DotEnvFromExample {
    if (Test-Path -LiteralPath $DotEnv) { return }
    if (-not (Test-Path -LiteralPath $Example)) {
        throw ".env missing and .env.example not found in $RepoRoot"
    }
    Copy-Item -LiteralPath $Example -Destination $DotEnv
    Write-Host "Created .env from .env.example (edit placeholder next)." -ForegroundColor Yellow
}

Ensure-DotEnvFromExample

Write-Host ""
Write-Host "  === Set OpenRouter API key (input hidden) ===" -ForegroundColor Cyan
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

$doubleQuote = [char]34
$singleQuote = [char]39

if ($plain.Length -ge 2 -and $plain[0] -eq $doubleQuote -and $plain[$plain.Length - 1] -eq $doubleQuote) {
    $plain = $plain.Substring(1, $plain.Length - 2).Trim()
}
if ($plain.Length -ge 2 -and $plain[0] -eq $singleQuote -and $plain[$plain.Length - 1] -eq $singleQuote) {
    $plain = $plain.Substring(1, $plain.Length - 2).Trim()
}

if ([string]::IsNullOrWhiteSpace($plain)) {
    Write-Host "  Cancelled - empty key." -ForegroundColor Yellow
    exit 1
}

if ((-not $plain.StartsWith("sk-")) -or $plain.Length -lt 30) {
    Write-Host "  NOTE:   This does not look like a typical OpenRouter key. Saving it anyway, then validating." -ForegroundColor Yellow
}

$lines = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $DotEnv -Encoding UTF8 | ForEach-Object { $lines.Add($_) }

$hadKey = $false
$hadBase = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*OPENAI_API_KEY\s*=') {
        $lines[$i] = "OPENAI_API_KEY=$plain"
        $hadKey = $true
    }
    if ($lines[$i] -match '^\s*OPENAI_BASE_URL\s*=') {
        $hadBase = $true
    }
}

if (-not $hadBase) {
    $lines.Add("OPENAI_BASE_URL=https://openrouter.ai/api/v1")
}

if (-not $hadKey) {
    $lines.Add("OPENAI_API_KEY=$plain")
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($DotEnv, $lines.ToArray(), $utf8NoBom)

$verify = (Get-Content -LiteralPath $DotEnv -Encoding UTF8 |
    Where-Object { $_ -match '^\s*OPENAI_API_KEY\s*=' } |
    Select-Object -First 1)
$verifyVal = if ($verify) { ($verify -replace '^\s*OPENAI_API_KEY\s*=\s*', '').Trim() } else { '' }
if ($verifyVal -ne $plain -or [string]::IsNullOrWhiteSpace($verifyVal)) {
    Write-Host ""
    Write-Host "  ERROR: .env round-trip check failed (saved value did not match)." -ForegroundColor Red
    Write-Host "  Path:   $DotEnv" -ForegroundColor Red
    Write-Host "  Hint:   close any other process holding .env (OneDrive sync, editor) and try UPDATE-KEY.bat." -ForegroundColor Red
    exit 4
}

$mask = if ($plain.Length -ge 12) { "$($plain.Substring(0, 6))...$($plain.Substring($plain.Length - 4))" } else { "(short)" }
Write-Host ""
Write-Host ("  Saved OPENAI_API_KEY to {0} (length {1}, fingerprint {2})" -f $DotEnv, $plain.Length, $mask) -ForegroundColor Green

if (-not $NoVerify) {
    Write-Host ""
    & (Join-Path $RepoRoot "validate-openrouter.ps1")
    $v = $LASTEXITCODE
    if ($v -eq 2) {
        Write-Host "  OpenRouter still rejected this key. Try again with UPDATE-KEY.bat" -ForegroundColor Red
        exit 2
    }
    if ($v -ne 0) {
        Write-Host "  OpenRouter did not validate this key yet (validator exit $v)." -ForegroundColor Yellow
        exit $v
    }
}

Write-Host ""
exit 0
