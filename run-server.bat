@echo off
setlocal
REM Explicit launcher for the optional Python surface (FastAPI server or chat CLI).
REM This is NOT part of the claw.exe pipeline: START-CLAW.bat and run-claw.bat
REM never call this. Run it only when you want the Python server.
REM   run-server.bat          starts the FastAPI server (127.0.0.1:8000)
REM   run-server.bat chat     starts the ClawCodex chat CLI
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0claw_bootstrap.ps1" %*
exit /b %errorlevel%
