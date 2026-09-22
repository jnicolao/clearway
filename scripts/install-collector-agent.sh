#!/bin/bash
# Install (or reinstall) the launchd agent that keeps the AIS collector alive.
#
#   ./scripts/install-collector-agent.sh            # install and start
#   ./scripts/install-collector-agent.sh --uninstall
#
# The collector has to run for six-plus weeks before the dwell-time work can
# start. A foreground terminal tab does not survive a closed window or a
# reboot; this does.
#
# KNOWN LIMITATION, verified 2026-09-21: this does NOT work while the repo
# lives under ~/Documents. That is a TCC-protected location, and a launchd
# agent has no grant for it even though Terminal does, so the wrapper dies
# with "Operation not permitted" before it runs. Nothing in this script can
# work around that. Two fixes, both outside this script:
#
#   1. Move the repo somewhere unprotected (~/Developer/clearway), or
#   2. Add /opt/homebrew/bin/uv to Full Disk Access in System Settings and
#      point ProgramArguments straight at uv, with the key moved into
#      EnvironmentVariables since there would be no shell to source .env.

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
LABEL="com.jnicolao.clearway.ais"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/clearway-ais.log"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array><string>$REPO/scripts/run-collector.sh</string></array>
    <key>WorkingDirectory</key><string>$REPO</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <!-- Without this launchd retries instantly and burns CPU while the
         network is down or another collector holds the lock. -->
    <key>ThrottleInterval</key><integer>30</integer>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "installed $LABEL"
echo "  plist : $PLIST"
echo "  log   : $LOG"
echo
echo "status : launchctl print gui/$(id -u)/$LABEL | head -20"
echo "logs   : tail -f $LOG"
echo "stop   : $0 --uninstall"
