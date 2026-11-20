@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Create .venv and install development dependencies first.
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest
exit /b %errorlevel%
