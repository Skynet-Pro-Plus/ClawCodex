@echo off
setlocal
REM Launches the packaged claw CLI via PowerShell (same folder as this .bat).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-claw.ps1" %*
