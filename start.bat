@echo off
rem Assignment Checker: starts the site connected to the course OneDrive folder.
rem Double-click this file. The first run installs what is needed (about a minute).
rem install-autostart.bat makes it start by itself, hidden, every time Windows starts.
rem Every run first updates the system from GitHub (main), so the whole team runs the same version, and updates Claude Code.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if exist ".git" (
  where git >nul 2>nul
  if errorlevel 1 (
    echo Git is not installed, so the system will not update itself. Install it: winget install Git.Git
  ) else (
    echo Updating from GitHub...
    git pull --ff-only -q >nul 2>nul
    if errorlevel 1 echo Could not update from GitHub. Starting the version that is on this computer.
  )
)

rem Claude Code (grading, and pulling from / uploading to Moodle) must be recent: an old version refuses the new models
set "CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe"
if not exist "%CLAUDE_EXE%" set "CLAUDE_EXE=claude"
"%CLAUDE_EXE%" --version >nul 2>nul
if not errorlevel 1 (
  echo Updating Claude Code...
  "%CLAUDE_EXE%" update >nul 2>nul
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: installing...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python is not installed. Install it from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
  )
)
rem Quick when nothing changed; installs what a new version added
".venv\Scripts\python" -m pip install --disable-pip-version-check -q -r requirements.txt

rem "start.bat background" (from autostart.vbs, at Windows sign-in): no browser, no window waiting for a key
if /i "%~1"=="background" (
  ".venv\Scripts\python" -m dashboard serve --no-open
  exit /b
)
".venv\Scripts\python" -m dashboard serve
pause
