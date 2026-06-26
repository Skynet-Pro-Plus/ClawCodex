@echo off
REM One-click Windows launcher: choose OpenRouter or Cerebras, validate key, start ClawCodex.
REM Windows-native only: claw.exe runs directly; WSL is never used.
setlocal
set "CLAW_NO_CREDENTIAL_PROMPT="
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="
set "CEREBRAS_API_KEY="
set "CLAW_SKIP_OPENROUTER_MODEL_PICKER="
cd /d "%~dp0"
title ClawCodex
echo.
echo  ClawCodex - choose a provider, then enter your API key or LM Studio settings in THIS window if asked.
echo  After "Initializing ClawCodex" appears, wait 10-30 seconds for the banner and ^> prompt.
echo  If you are never asked for a key, run:  powershell -File build-claw.ps1   then try again.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-claw.ps1"
set CLAW_LAUNCH_EXIT=%errorlevel%

echo.
echo  Examples in this window:
echo    run-claw.bat
echo    run-claw.bat prompt "say hello"
echo.
if "%CLAW_LAUNCH_EXIT%"=="0" (
    echo  ClawCodex session ended. You can run run-claw.bat again from here.
    echo.
) else (
    echo  Claw exited with code %CLAW_LAUNCH_EXIT%.
    echo.
)
cmd /k
