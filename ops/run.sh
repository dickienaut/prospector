#!/usr/bin/env bash
#
# Prospector scheduled-run wrapper — the single thing launchd invokes (com.prospector.run.plist).
#
# Why a wrapper, not `uv run pros run` directly: launchd runs with a MINIMAL environment and does not
# source your shell profile, so the two classic failures are (a) `uv` not on PATH and (b) the wrong
# working directory (config/prospector.yaml and .env are cwd-relative — a missing .env means no Tiingo
# token). This script fixes both, then runs one tick + the fossil-store backup.
#
# One scheduled entity, on purpose: this wrapper (via ONE plist) is the only scheduled thing. If it fires
# everything fires; if it dies everything dies — so a missing weekly heartbeat unambiguously attests "the
# runner is dead," which is exactly the property the §8a dead-man needs (two plists could let the heartbeat
# die while daily runs continue — ambiguity in the one channel whose job is unambiguous absence).
# See docs/decisions/2026-07-12-m7-autonomy-core.md.
set -euo pipefail

# Repo root = the parent of ops/ (this script's dir), symlinks resolved, so it works wherever launchd runs it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
cd "$REPO_ROOT"   # so ./config/prospector.yaml and ./.env resolve

# Make `uv` findable under launchd's minimal PATH (installers land it in one of these).
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "=== prospector run $(date -u '+%Y-%m-%dT%H:%M:%SZ') · cwd=$REPO_ROOT ==="

# The weekly heartbeat rides an actual run so a received email proves the whole pipeline ran (§8a/§10).
# Which day is heartbeat day is decided HERE (external to the runner's --heartbeat flag) — Sunday.
# keep in sync with config `schedule.weekly_day` (SUN); `date +%u` gives 1=Mon … 7=Sun.
if [ "$(date +%u)" -eq 7 ]; then
  uv run pros run --heartbeat
else
  uv run pros run
fi

# Back up the fossil store after the run — the backup cadence deliberately lives here, not inside `pros run`
# (store-durability decision). `set -e` above means a failed run exits before this: the run's own dead-man
# email has already fired, and the next successful cycle backs up (the store is append-only, nothing lost).
# `pros backup` faults loudly (non-zero) until the Mini's backup.targets are blessed — never a silent no-op.
uv run pros backup
