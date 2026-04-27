@echo off
REM One-click Windows launcher: runs first-time setup, then starts Claw.
REM If OpenRouter is not configured, claw asks once and saves .env (see USAGE.md).
REM Rebuild bin\windows\claw.exe with .\build-claw.ps1 if doctor never prompts for a key.
setlocal
set "CLAW_NO_CREDENTIAL_PROMPT="
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="
cd /d "%~dp0"
title ClawCodex
echo.
echo  ClawCodex - first health check. If asked for an API key, type it in THIS window ^(no pop-up^).
echo  If you are never asked, run:  powershell -File build-claw.ps1   then try again.
echo.

:check_openrouter
echo  Checking OpenRouter key ^(live request when a key is set^)...
echo  Command:
echo    powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\validate-openrouter.ps1"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0validate-openrouter.ps1"
set CLAW_OR_VALID=%errorlevel%
if "%CLAW_OR_VALID%"=="0" goto openrouter_ok
if "%CLAW_OR_VALID%"=="10" (
    echo.
    echo  No valid OpenRouter key is saved yet.
    goto prompt_openrouter_key
)
if "%CLAW_OR_VALID%"=="2" (
    echo.
    echo  OpenRouter rejected your saved API key ^(HTTP 401/403^).
    goto prompt_openrouter_key
)
if "%CLAW_OR_VALID%"=="3" (
    echo.
    echo  OpenRouter did not return a usable response.
    echo  If this repeats, check internet / VPN / firewall.
    goto prompt_openrouter_key
)
echo.
echo  Unexpected OpenRouter validation exit code: %CLAW_OR_VALID%
goto prompt_openrouter_key

:prompt_openrouter_key
echo.
echo  Enter or replace your OpenRouter API key now. Input is hidden.
echo  Press Enter on an empty line to cancel.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set-openrouter-key.ps1" -NoVerify
set CLAW_KEY_SET=%errorlevel%
if "%CLAW_KEY_SET%"=="4" (
    echo.
    echo  The key was entered, but .env did not save it correctly.
    echo  Close editors or sync tools touching .env, then run UPDATE-KEY.bat.
    goto after_claw
)
if not "%CLAW_KEY_SET%"=="0" (
    echo.
    echo  Key setup was cancelled or failed. Claw will not launch until a valid key is saved.
    echo  Run START-CLAW.bat again, or run UPDATE-KEY.bat.
    goto after_claw
)
echo.
goto check_openrouter

:openrouter_ok
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
