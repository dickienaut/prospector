#!/usr/bin/env bash
#
# Install the Prospector scheduled runner as a macOS LaunchAgent from com.prospector.run.plist.
#
# Run this FROM the PRODUCTION checkout — the clone pinned at the v1.0.0 tag (see ops/README.md) — so the
# installed plist's paths point at production, never your dev clone on main.
#
#   ./ops/install.sh <LOCAL_HOUR 0-23> <LOCAL_MINUTE 0-59>
#
# HH:MM is the Mini's LOCAL-time equivalent of config schedule.daily_utc (22:30 UTC, after US close).
set -euo pipefail

HOUR="${1:?usage: ops/install.sh <LOCAL_HOUR 0-23> <LOCAL_MINUTE 0-59>  (local equivalent of 22:30 UTC)}"
MINUTE="${2:?usage: ops/install.sh <LOCAL_HOUR 0-23> <LOCAL_MINUTE 0-59>  (local equivalent of 22:30 UTC)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
TEMPLATE="$SCRIPT_DIR/com.prospector.run.plist"
LABEL="com.prospector.run"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
STDOUT="$LOG_DIR/$LABEL.out.log"
STDERR="$LOG_DIR/$LABEL.err.log"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

# Substitute placeholders → the installed plist (# delimiter: paths contain /).
sed -e "s#__PROSPECTOR_ROOT__#$REPO_ROOT#g" \
    -e "s#__HOUR__#$HOUR#g" \
    -e "s#__MINUTE__#$MINUTE#g" \
    -e "s#__STDOUT__#$STDOUT#g" \
    -e "s#__STDERR__#$STDERR#g" \
    "$TEMPLATE" > "$DEST"

# Validate before loading — a malformed plist just fails silently in launchd otherwise.
plutil -lint "$DEST"

# Idempotent (re)install: bootout any existing agent, then bootstrap the new one.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"

printf 'installed %s\n' "$DEST"
printf '  runs:  %s/ops/run.sh   daily at LOCAL %02d:%02d\n' "$REPO_ROOT" "$HOUR" "$MINUTE"
printf '  logs:  %s  ·  %s\n' "$STDOUT" "$STDERR"
printf 'verify: launchctl print gui/%s/%s   (activation + acceptance: ops/README.md)\n' "$(id -u)" "$LABEL"
