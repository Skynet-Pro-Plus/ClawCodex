@echo off
REM Opens a NEW Command Prompt in this repo folder, shows the full check command, then runs it.
setlocal
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="
start "ClawCodex - OpenRouter key check" /D "%~dp0" cmd /k call CHECK-KEY.bat
