#!/usr/bin/env bash
#
# Remove the Prospector scheduled runner LaunchAgent (stops it firing; does not touch the store).
set -euo pipefail

LABEL="com.prospector.run"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$DEST"
printf 'removed %s (LaunchAgent booted out)\n' "$DEST"
