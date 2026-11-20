@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Create .venv and install the package first. See README.md.
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run dashboard\app.py --server.address 127.0.0.1
exit /b %errorlevel%
