#Requires -Version 5.1
<#
.SYNOPSIS
  Rebuild claw.exe from source and refresh bin\windows\claw.exe.

.DESCRIPTION
  Runs `cargo build --release -p rusty-claude-cli` under rust\, then copies
  rust\target\release\claw.exe to bin\windows\claw.exe.
  Requires Rust (cargo) on PATH: https://rustup.rs/
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RustDir = Join-Path $RepoRoot "rust"
$ReleaseExe = Join-Path $RustDir "target\release\claw.exe"
$OutExe = Join-Path $RepoRoot "bin\windows\claw.exe"

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Host "cargo not found. Install Rust from https://rustup.rs/ then reopen this terminal." -ForegroundColor Red
    exit 1
}

Push-Location $RustDir
try {
    Write-Host "Building release rusty-claude-cli (claw)..." -ForegroundColor Cyan
    cargo build --release -p rusty-claude-cli
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $ReleaseExe)) {
    Write-Host "Expected output not found: $ReleaseExe" -ForegroundColor Red
    exit 1
}

$outDir = Split-Path $OutExe -Parent
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Copy-Item -LiteralPath $ReleaseExe -Destination $OutExe -Force
Write-Host "Updated: $OutExe" -ForegroundColor Green
