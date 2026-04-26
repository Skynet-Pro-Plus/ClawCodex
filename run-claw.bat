@echo off
setlocal
REM Run the packaged CLI from repo root (Command Prompt — no PowerShell).
REM Ensures .env beside README.md is found and matches run-claw.ps1 cwd behavior.
cd /d "%~dp0"
set "EXE=%~dp0bin\windows\claw.exe"
if not exist "%EXE%" (
    echo Missing: %EXE%
    echo From PowerShell in this repo folder, run:  .\build-claw.ps1
    echo That copies rust\target\release\claw.exe here. Requires Rust ^(cargo^) on PATH.
    exit /b 1
)
"%EXE%" %*
