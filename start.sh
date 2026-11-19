#!/bin/bash
# Bodek Hacham (the checking system) on a Mac: starts the site connected to the course OneDrive folder.
# The Mac twin of start.bat. Run it in Terminal:  bash start.sh
# install-autostart.sh makes it start by itself, hidden, every time you log in (a LaunchAgent runs "start.sh background").
# Every run first updates the system from GitHub (main), so the whole team runs the same version, and updates Claude Code.
cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8
export LANG="${LANG:-en_US.UTF-8}"
# launchd starts this with a bare PATH: add where Claude Code, uv, 7zz (~/.local/bin) and Homebrew live
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
HEALTH="http://127.0.0.1:8765/api/health"

if [ "$1" = "background" ]; then
  # From the LaunchAgent, which runs this again whenever it ends (KeepAlive). A system that already answers (someone
  # started it by hand) is left alone: wait a minute and end, and launchd asks again. Like autostart.vbs's minute loop
  if curl -fsS -m 5 "$HEALTH" >/dev/null 2>&1; then
    sleep 60
    exit 0
  fi
  # The LaunchAgent appends to this log (install-autostart.sh). Kept small: only starts and errors go there
  LOG="$HOME/Library/Logs/bodek-hacham.log"
  if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 5000000 ]; then : > "$LOG"; fi
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') starting"
fi

if [ -d .git ]; then
  if git --version >/dev/null 2>&1; then
    echo "Updating from GitHub..."
    git pull --ff-only -q >/dev/null 2>&1 || echo "Could not update from GitHub. Starting the version that is on this computer."
  else
    echo "Git is not installed, so the system will not update itself. Run: xcode-select --install"
  fi
fi

# Claude Code (grading, and pulling from / uploading to Moodle) must be recent: an old version refuses the new models.
# The update can hang (2026-11-03: over 5 minutes on Windows), so it gets CLAUDE_UPDATE_WAIT_S seconds and is then stopped
CLAUDE_EXE="$HOME/.local/bin/claude"
[ -x "$CLAUDE_EXE" ] || CLAUDE_EXE="claude"
WAIT="${CLAUDE_UPDATE_WAIT_S:-120}"
if "$CLAUDE_EXE" --version >/dev/null 2>&1; then
  echo "Updating Claude Code..."
  "$CLAUDE_EXE" update >/dev/null 2>&1 &
  pid=$!
  waited=0
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$WAIT" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -9 -P "$pid" 2>/dev/null
    kill -9 "$pid" 2>/dev/null
    echo "Claude Code did not finish updating within $WAIT seconds. Skipped: the version on this computer is used."
  fi
  wait "$pid" 2>/dev/null
fi

# A Python of 3.10 or newer: one that is installed, or uv's own (connect.sh installs uv when there is none).
# The Python of Apple's command line tools is 3.9, too old
good_python() {
  for py in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

if [ ! -x .venv/bin/python ]; then
  echo "First run: installing..."
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --seed --python 3.12 .venv
  fi
  if [ ! -x .venv/bin/python ] && PY="$(good_python)"; then
    "$PY" -m venv .venv
  fi
  if [ ! -x .venv/bin/python ]; then
    echo "Python 3.10 or newer is not installed. Run the Mac connect command again (it installs it):"
    echo "  curl -fsSL https://bodek-hacham.vercel.app/connect.sh | bash"
    exit 1
  fi
fi
# Quick when nothing changed; installs what a new version added
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt

if [ "$1" = "background" ]; then
  exec .venv/bin/python -m dashboard serve --no-open
fi
.venv/bin/python -m dashboard serve
