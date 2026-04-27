@echo off
REM CLI-friendly: prompt for OpenRouter key (hidden), save to .env, then live-verify.
setlocal
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="
cd /d "%~dp0"
title ClawCodex - update OpenRouter key
echo.
echo  Command:
echo    powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\set-openrouter-key.ps1"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\set-openrouter-key.ps1"
echo.
pause
