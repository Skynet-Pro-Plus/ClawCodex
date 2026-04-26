@echo off
setlocal
REM Always run from the repo root so .env and workspace resolution match this folder
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-claw.ps1" %*
