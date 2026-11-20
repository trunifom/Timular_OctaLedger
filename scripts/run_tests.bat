@echo off
setlocal
rem Quality gate: tests, lint, formatting check and strict typing. All four must pass.
rem (The GUI tests take a few minutes because every AppTest run executes a real page.)
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Create .venv and install development dependencies first.
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest || exit /b 1
".venv\Scripts\python.exe" -m ruff check . || exit /b 1
".venv\Scripts\python.exe" -m ruff format --check . || exit /b 1
".venv\Scripts\python.exe" -m mypy || exit /b 1
echo.
echo Quality gate passed.
exit /b 0
