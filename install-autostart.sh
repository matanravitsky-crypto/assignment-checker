#!/bin/bash
# Once per Mac: the system starts by itself, hidden, every time you log in, so https://bodek-hacham.vercel.app works
# right away. Starts it now too. The Mac twin of install-autostart.bat + autostart.vbs:
# a LaunchAgent (~/Library/LaunchAgents/com.bodek-hacham.server.plist) runs "start.sh background", and launchd runs it
# again whenever it ends (the server crashed, or stopped itself to take an update: dashboard/updater.py).
# What start.sh prints goes to ~/Library/Logs/bodek-hacham.log.
# To undo:  launchctl bootout gui/$(id -u)/com.bodek-hacham.server ; rm ~/Library/LaunchAgents/com.bodek-hacham.server.plist
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.bodek-hacham.server"  # as LAUNCH_AGENT in dashboard/updater.py
AGENTS="$HOME/Library/LaunchAgents"
PLIST="$AGENTS/$LABEL.plist"
LOG="$HOME/Library/Logs/bodek-hacham.log"
DOMAIN="gui/$(id -u)"

xml() { local s="$1"; s="${s//&/&amp;}"; s="${s//</&lt;}"; s="${s//>/&gt;}"; printf '%s' "$s"; }

mkdir -p "$AGENTS" "$(dirname "$LOG")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$(xml "$DIR/start.sh")</string>
    <string>background</string>
  </array>
  <key>WorkingDirectory</key><string>$(xml "$DIR")</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$(xml "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOG")</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$(xml "$HOME/.local/bin"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LANG</key><string>en_US.UTF-8</string>
  </dict>
</dict>
</plist>
EOF
if ! plutil -lint "$PLIST" >/dev/null; then
  echo "Could not write $PLIST"
  exit 1
fi

# Load it again from the new file (a second run replaces the old one), which also starts it now (RunAtLoad)
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 && sleep 2
if ! launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null; then
  launchctl load -w "$PLIST" 2>/dev/null  # older macOS
fi
if ! launchctl list "$LABEL" >/dev/null 2>&1; then
  echo "Could not add the system to the Mac's login items. What launchd said: launchctl print $DOMAIN/$LABEL"
  exit 1
fi
echo "The system will now start by itself whenever you log in to this Mac, and it is starting now."
echo "Open https://bodek-hacham.vercel.app in a minute (the first start installs what is needed)."
