@echo off
setlocal
REM Run the packaged CLI from repo root (Command Prompt - no PowerShell).
REM Windows-native only: claw.exe runs directly. WSL is never used or probed.
REM Credentials live in repo-root .env (see USAGE.md); claw reads it from cwd.
cd /d "%~dp0"
set "EXE=%~dp0bin\windows\claw.exe"
if not exist "%EXE%" (
    echo Missing: %EXE%
    echo From PowerShell in this repo folder, run:  .\build-claw.ps1
    echo That copies rust\target\release\claw.exe here. Requires Rust ^(cargo^) on PATH.
    exit /b 1
)
"%EXE%" %*
exit /b %errorlevel%
