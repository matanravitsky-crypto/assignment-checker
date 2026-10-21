@echo off
rem Assignment Checker: starts the site connected to the course OneDrive folder.
rem Double-click this file. The first run installs what is needed (about a minute).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: installing...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python is not installed. Install it from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python" -m pip install --disable-pip-version-check -q -r requirements.txt
)

".venv\Scripts\python" -m pipeline serve
pause
