@echo off
setlocal
rem Starts the dashboard in the browser (http://127.0.0.1:8501, local only, no telemetry).
rem The agent must be running (scripts\start_agent.bat) - closing the dashboard never stops tracking.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Create .venv and install the package first. See docs\INSTALLATION.md.
  exit /b 1
)
".venv\Scripts\python.exe" -m octaledger dashboard %*
exit /b %errorlevel%
