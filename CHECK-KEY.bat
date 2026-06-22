@echo off
REM Quick terminal check: missing / placeholder / rejected / accepted OpenRouter key.
setlocal
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="
cd /d "%~dp0"
title ClawCodex - OpenRouter key check

echo.
echo  ------------------------------------------------------------------
echo   OpenRouter live check - command you can copy into PowerShell:
echo  ------------------------------------------------------------------
echo.
echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0validate-openrouter.ps1"
echo.
echo  ------------------------------------------------------------------
echo   Running that command now...
echo  ------------------------------------------------------------------
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0validate-openrouter.ps1"
set OR_EXIT=%errorlevel%

echo.
echo  Exit code: %OR_EXIT%  ^(0 = OK, 10 = missing, 2 = rejected, 3 = no response^)
echo.
pause
