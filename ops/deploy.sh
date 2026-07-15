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
#     never be silently pinned to a moving ref.
# Machine-local config (the per-machine paths store.root and backup.targets) lives in the untracked,
# gitignored overlay config/prospector.local.yaml — a checkout never touches an untracked+ignored file,
# so it survives every deploy with no stash/pop. The tracked config/prospector.yaml carries only defaults.
#
# The next scheduled run picks up the new code automatically (run.sh runs `uv run` fresh each fire — no
# restart). Override the worktree path with PROSPECTOR_PROD=… if it isn't ~/prospector/prod.
set -euo pipefail

TAG="${1:?usage: ops/deploy.sh <tag>   (a release TAG, e.g. v1.0.1 — never a branch or SHA)}"
PROD="${PROSPECTOR_PROD:-$HOME/prospector/prod}"

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

# --- 3. move the worktree to the tag. Machine-local config is in the untracked, gitignored overlay
#        config/prospector.local.yaml, which a checkout leaves untouched — so it survives with no
#        stash/pop. The tracked config must stay CLEAN (defaults only); local edits to it would make the
#        checkout abort, so STOP with guidance (this also catches a not-yet-migrated prod worktree).
if ! git -C "$PROD" diff --quiet -- config/prospector.yaml; then
  echo "STOP: ${PROD}/config/prospector.yaml has local edits, but machine-local config now lives in the" >&2
  echo "      UNTRACKED overlay config/prospector.local.yaml. Move store.root / backup.targets into that" >&2
  echo "      overlay, then \`git -C ${PROD} checkout -- config/prospector.yaml\` to reset the tracked file." >&2
  echo "      See docs/decisions/2026-07-12-local-config-overlay.md." >&2
  exit 3
fi
# --- 3b+4. Under the SINGLE-WRITER LOCK (M7-04): a deploy must never swap code/deps under an in-flight
#     scheduled tick. Take the SAME lock the runner holds — `pros store lock-run` (prospector.store.run_lock,
#     fcntl.flock), macOS-PORTABLE (the shell `flock(1)` util does not exist on macOS). Run from the DEV repo
#     (this release's code + its current venv, so the command exists even on the first deploy of this
#     feature); on the Mini, dev and prod share the ONE external store, so the lock path the dev derives
#     matches the prod runner's. The checkout + `uv sync` run TOGETHER under one hold. On contention: refuse
#     and retry, never wait silently (`lock-run` exits 75 = EX_TEMPFAIL).
if ! ( cd "$REPO" && uv run pros store lock-run -- \
        bash -euo pipefail -c '
          git -C "$0" checkout --quiet --detach "$1"
          cd "$0" && uv sync --locked
        ' "$PROD" "$TAG" ); then
  rc=$?
  if [ "$rc" -eq 75 ]; then
    echo "STOP: a scheduled tick is in flight (single-writer lock held) — retry the deploy in a few minutes." >&2
  else
    echo "ERROR: deploy mutation (checkout / uv sync) failed under the lock — see the message above." >&2
  fi
  exit 4
fi
echo "deployed ${TAG} → ${PROD}"
echo "  worktree HEAD: $(git -C "$PROD" rev-parse --short HEAD)  (detached at ${TAG})"
echo "  the scheduler runs the new code on its next fire (run.sh runs \`uv run\` fresh — no restart needed)."
