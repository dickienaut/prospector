#!/usr/bin/env bash
#
# ops/deploy.sh <tag> — ship a release to the production WORKTREE. Run from the dev repo.
#
# Production is a git worktree (~/prospector/prod) pinned at a release TAG — one repo, two working dirs,
# not a second clone (see docs/decisions/2026-07-12-production-worktree-and-deploy.md). This is the ONE
# command that moves production to a new release, so you almost never touch the prod dir by hand.
#
# It enforces deploy-from-tag by MECHANISM, not memory:
#   - it REFUSES any ref that isn't a tag (a bare branch or SHA is rejected up front), so production can
#     never be silently pinned to a moving ref;
#   - it PRESERVES the worktree's machine-local config (store.root, backup.targets in config/prospector.yaml)
#     across the checkout, and STOPS loudly if a release changed that file upstream — never a silent wipe.
#
# The next scheduled run picks up the new code automatically (run.sh runs `uv run` fresh each fire — no
# restart). Override the worktree path with PROSPECTOR_PROD=… if it isn't ~/prospector/prod.
set -euo pipefail

TAG="${1:?usage: ops/deploy.sh <tag>   (a release TAG, e.g. v1.0.1 — never a branch or SHA)}"
PROD="${PROSPECTOR_PROD:-$HOME/prospector/prod}"
CFG="config/prospector.yaml"

# The dev repo this script lives in (fetch here; it shares .git with the worktree, so tags reach both).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

git -C "$REPO" fetch --tags --quiet origin

# --- 1. TAG-ONLY. refs/tags/<tag> must resolve to a commit; a branch/SHA does not live there → rejected.
if ! git -C "$REPO" rev-parse --verify --quiet "refs/tags/${TAG}^{commit}" >/dev/null; then
  echo "ERROR: '${TAG}' is not a tag — production deploys only from a release tag (never a branch or SHA)." >&2
  echo "       available tags: $(git -C "$REPO" tag --list | tr '\n' ' ')" >&2
  exit 2
fi

# --- 2. the production worktree must exist (created once with `git worktree add`).
if [ ! -d "$PROD" ] || ! git -C "$PROD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: no git worktree at ${PROD}. Create it once (from the dev repo):" >&2
  echo "       git worktree add ${PROD} ${TAG}" >&2
  exit 2
fi

# --- 3. preserve the worktree's machine-local config across the checkout. A bare checkout would clobber
#        store.root / backup.targets; stash → checkout → pop. If the tag CHANGED config upstream, the pop
#        conflicts and we stop loudly (reconcile deliberately — never a silent machine-config wipe).
stashed=0
if ! git -C "$PROD" diff --quiet -- "$CFG"; then
  git -C "$PROD" stash push --quiet -- "$CFG"
  stashed=1
fi

git -C "$PROD" checkout --quiet --detach "$TAG"

if [ "$stashed" -eq 1 ] && ! git -C "$PROD" stash pop --quiet 2>/dev/null; then
  echo "STOP: '${TAG}' changed ${CFG} upstream and it conflicts with this machine's local config." >&2
  echo "      Your machine config is safe in the stash — reconcile ${CFG} in ${PROD} by hand (keep" >&2
  echo "      store.root / backup.targets), then \`git -C ${PROD} stash drop\`. Not deploying blindly." >&2
  exit 3
fi

# --- 4. sync deps from the tag's lockfile, and report.
( cd "$PROD" && uv sync --locked )
echo "deployed ${TAG} → ${PROD}"
echo "  worktree HEAD: $(git -C "$PROD" rev-parse --short HEAD)  (detached at ${TAG})"
echo "  the scheduler runs the new code on its next fire (run.sh runs \`uv run\` fresh — no restart needed)."
