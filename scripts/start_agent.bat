@echo off
setlocal
rem Starts the OctaLedger agent (background tracking, database, local API).
rem Keep this window open while you work; close it (or press Ctrl+C) to stop the agent.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Create .venv and install the package first. See docs\INSTALLATION.md.
  exit /b 1
)
".venv\Scripts\python.exe" -m octaledger agent %*
exit /b %errorlevel%
