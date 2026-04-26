@echo off
REM One-click Windows launcher: runs first-time setup, then starts Claw.
REM If OpenRouter is not configured, claw asks once and saves .env (see USAGE.md).
REM Rebuild bin\windows\claw.exe with .\build-claw.ps1 if doctor never prompts for a key.
setlocal
set "CLAW_NO_CREDENTIAL_PROMPT="
cd /d "%~dp0"
title ClawCodex
echo.
echo  ClawCodex — first health check. If asked for an API key, type it in THIS window ^(no pop-up^).
echo  If you are never asked, run:  powershell -File build-claw.ps1   then try again.
echo.
call "%~dp0run-claw.bat" doctor
if errorlevel 1 goto after_claw
echo.
echo  Starting Claw...
echo.
call "%~dp0run-claw.bat"

:after_claw
echo.
echo  Examples in this window:
echo    run-claw.bat
echo    run-claw.bat prompt "say hello"
echo.
cmd /k
