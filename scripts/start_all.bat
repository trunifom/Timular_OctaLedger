@echo off
setlocal
rem Convenience: start the agent in its own window, then the dashboard in this one.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Create .venv and install the package first. See docs\INSTALLATION.md.
  exit /b 1
)
start "OctaLedger Agent" ".venv\Scripts\python.exe" -m octaledger agent
rem Give the agent a moment to create the API token on the very first start.
timeout /t 3 /nobreak >nul
".venv\Scripts\python.exe" -m octaledger dashboard
exit /b %errorlevel%
