#!/bin/bash
# Bodek Hacham (the checking system): connects this Mac in one step, so the site's buttons run here,
# through this person's own Claude. The Mac twin of connect.ps1.
#   In Terminal:  curl -fsSL https://bodek-hacham.vercel.app/connect.sh | bash
# Once per Mac. Running it again only adds what is missing and opens the site.
#   1. Installs what the system needs, if it is missing, with no password: Git (Apple's command line tools: a window
#      asks to install them), Python 3.12 (through uv, when there is no Python 3.10+), 7-Zip (7-zip.org's own build,
#      checked by its SHA-256) and Claude Code (Anthropic's own installer, the same one the site's button runs).
#      Everything goes to ~/.local/bin.
#   2. Downloads the system from GitHub to ~/Bodek Hacham/assignment-checker (a Mac that already has it keeps its folder).
#   3. install-autostart.sh: the system starts by itself, hidden, whenever you log in. It starts now too.
#   4. Opens the site in Chrome, connected to this Mac.
# BODEK_BRANCH=<branch> before "bash" downloads that branch instead of main (to try a change before it is merged).
# No passwords go through this script. Messages are in English: Terminal prints Hebrew backwards.
# Everything is inside main(), which runs only after the whole script arrived: a cut download runs nothing.

main() {
  local repo="https://github.com/matanravitsky-crypto/assignment-checker"
  local site="https://bodek-hacham.vercel.app/#/pull"  # the site talks to the system on this Mac; Chrome asks once to allow it
  local health="http://127.0.0.1:8765/api/health"
  local label="com.bodek-hacham.server"  # as in install-autostart.sh
  local plist="$HOME/Library/LaunchAgents/$label.plist"
  local log="$HOME/Library/Logs/bodek-hacham.log"
  local bin="$HOME/.local/bin"
  local wait_minutes=8  # the first start downloads Python and its packages and updates Claude Code
  local seven_url="https://www.7-zip.org/a/7z2501-mac.tar.xz"  # 7-Zip 25.01 for macOS (arm64 + x86-64)
  local seven_sha="26aa75bc262bb10bf0805617b95569c3035c2c590a99f7db55c7e9607b2685e0"

  say() { printf '  %s\n' "$1"; }
  step() { printf '\n\033[36m> %s\033[0m\n' "$1"; }
  fail() { printf '\n  \033[33m%s\033[0m\n' "$1"; }
  have() { command -v "$1" >/dev/null 2>&1; }
  up() { curl -fsS -m 5 "$health" 2>/dev/null; }
  good_python() {  # as in start.sh: Apple's own python3 is 3.9, too old
    local py
    for py in python3.13 python3.12 python3.11 python3.10 python3; do
      if have "$py" && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then return 0; fi
    done
    return 1
  }

  if [ "$(uname -s)" != "Darwin" ]; then
    fail "This command is for a Mac. On Windows, in PowerShell: irm https://bodek-hacham.vercel.app/connect.ps1 | iex"
    return 1
  fi
  export PATH="$bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
  mkdir -p "$bin"

  printf '\n\033[32mBodek Hacham: connecting this Mac\033[0m\n'

  step "What the system needs"
  if git --version >/dev/null 2>&1; then say "Git - ok"; else
    xcode-select --install >/dev/null 2>&1
    fail "Git is missing. A window opened to install Apple's command line tools: click Install, wait until it"
    fail "finishes (a few minutes), then run this command again."
    return 1
  fi

  if good_python || have uv; then say "Python - ok"; else
    say "Python - installing (uv, with Python 3.12)..."
    curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | env UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1
    if have uv; then say "Python - installed (the system's first start downloads Python 3.12 through uv)"; else
      fail "Python did not install. Install Python 3.12 from https://www.python.org/downloads/macos/ and run this again."
      return 1
    fi
  fi

  if have 7zz || have 7z; then say "7-Zip - ok"; else
    say "7-Zip - installing..."
    local tmp
    tmp="$(mktemp -d)"
    if curl -fsSL -m 120 -o "$tmp/7z.tar.xz" "$seven_url" \
       && [ "$(shasum -a 256 "$tmp/7z.tar.xz" | cut -d' ' -f1)" = "$seven_sha" ] \
       && tar -xf "$tmp/7z.tar.xz" -C "$tmp" 7zz && mv "$tmp/7zz" "$bin/7zz" && chmod +x "$bin/7zz"; then
      say "7-Zip - installed"
    else
      say "7-Zip - not installed (needed only to pull from Moodle). Later: brew install sevenzip"
    fi
    rm -rf "$tmp"
  fi

  if have claude || [ -x "$bin/claude" ]; then say "Claude Code - ok"; else
    say "Claude Code - installing (Anthropic installer)..."
    curl -fsSL https://claude.ai/install.sh 2>/dev/null | bash >/dev/null 2>&1
    if have claude || [ -x "$bin/claude" ]; then say "Claude Code - installed"; else
      say "Claude Code - not installed yet: the site offers to install it on the first pull."
    fi
  fi

  if [ -d "/Applications/Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ]; then say "Chrome - ok"; else
    say "Chrome - not found. The site and Claude in Chrome need it: https://www.google.com/chrome/"
  fi

  local state
  state="$(up)"
  if [ -n "$state" ]; then
    step "The system is already running on this Mac"
  else
    step "The system"
    local dir=""
    if [ -f "$plist" ]; then  # install-autostart.sh already ran here: keep that folder, never a second copy
      dir="$(/usr/libexec/PlistBuddy -c 'Print :WorkingDirectory' "$plist" 2>/dev/null)"
      [ -f "$dir/start.sh" ] || dir=""
    fi
    [ -n "$dir" ] || dir="$HOME/Bodek Hacham/assignment-checker"
    if [ -d "$dir/.git" ]; then
      say "Folder: $dir (already here)"
      if [ -n "$BODEK_BRANCH" ]; then
        git -C "$dir" fetch -q origin && git -C "$dir" checkout -q "$BODEK_BRANCH" && git -C "$dir" pull -q --ff-only
        say "Branch: $(git -C "$dir" rev-parse --abbrev-ref HEAD)"
      fi
    elif [ -e "$dir" ]; then
      fail "$dir exists but is not the system's folder. Move it away and run this again."
      return 1
    else
      say "Downloading to $dir ..."
      mkdir -p "$(dirname "$dir")"
      local args=(clone -q)
      [ -n "$BODEK_BRANCH" ] && args+=(--branch "$BODEK_BRANCH")
      git "${args[@]}" "$repo" "$dir" </dev/null
      if [ ! -f "$dir/start.sh" ]; then
        fail "Could not download the system from $repo. Check the internet connection and run this again."
        return 1
      fi
    fi

    step "Starting it, and with every login from now on"
    if ! bash "$dir/install-autostart.sh"; then
      fail "Could not add the system to the Mac's login items."
      return 1
    fi
    say "The first start installs what it needs. This can take a few minutes"
    local deadline=$(( $(date +%s) + wait_minutes * 60 ))
    while [ -z "$state" ] && [ "$(date +%s)" -lt "$deadline" ]; do
      sleep 5
      printf '.'
      state="$(up)"
    done
    printf '\n'
    if [ -z "$state" ]; then
      fail "The system did not answer within $wait_minutes minutes. What it printed is in $log"
      fail "Run this command again in a few minutes, or send that file to the team."
      return 1
    fi
    say "Running."
  fi

  if ! printf '%s' "$state" | grep -q '"root": *"'; then
    fail "The course's OneDrive folder was not found on this Mac, so the site has nothing to show yet."
    fail "In the browser, open the YallaLinearit folder the lecturer shared and click Sync (or \"Add shortcut to My"
    fail "files\"); in the OneDrive app, sign in with the university account. If OneDrive cannot add it, tell the team."
  fi

  step "Opening the site"
  # In the background: "open" can wait for Chrome to finish starting (it never returned on a fresh macOS runner,
  # 2026-11-19), and nothing after it needs Chrome
  ( open -a "Google Chrome" "$site" 2>/dev/null || open "$site" ) >/dev/null 2>&1 &
  say 'Chrome asks once whether the site may access apps and services on this device: click "Allow".'
  say 'macOS may also say that "bash" was added to the login items: that is the system, starting with the Mac.'
  say 'In the site press "pull". The first time, it signs Claude Code in to YOUR Claude account and checks'
  say 'the Claude in Chrome extension; after that every pull runs through your own Claude, in your own Chrome.'
  printf '\n'
}

main "$@"
