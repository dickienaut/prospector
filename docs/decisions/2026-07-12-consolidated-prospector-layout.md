# Prospector's on-disk layout is consolidated under `~/prospector/{dev,prod,store}`

*Decision record, 2026-07-12. Pins the concrete paths for the worktree + tag-only deploy model
(`2026-07-12-production-worktree-and-deploy.md`), superseding that record's **example** paths
(`~/prospector-prod`, `~/prospector-store`, dev at `~/Documents/coding/prospector`). Amends `ops/README.md`'s
"deploy-from-tag shape" section and the `~/prospector-prod` default in `ops/deploy.sh`. The core decision is
unchanged — this only fixes where the pieces live. Design thread concurring.*

## The problem it fixes

The worktree model was ratified with **illustrative** paths (`~/prospector-prod`, `~/prospector-store`).
On the actual machine everything was set up consolidated under one parent — `~/prospector/{dev,prod,store}` —
but the scripts and docs still read the old scattered paths. That left a real footgun: `ops/deploy.sh`
defaulted `PROSPECTOR_PROD` to `~/prospector-prod`, so the next `ops/deploy.sh <tag>` would fail
("no git worktree") on a machine whose worktree is at `~/prospector/prod`. A vigilance tax hiding inside a
mechanism built to remove vigilance tax — the exact wrong place for it.

## The decision

**One parent directory, three siblings:**

```
~/prospector/
  dev/     git repo, branch `main`          — the dev clone (develop here; PR → main)
  prod/    git worktree, detached @ tag      — the scheduler runs here (WorkingDirectory)
  store/   the fossil store                  — external to BOTH checkouts (the one canonical store)
```

This satisfies every invariant of the ratified model with tidier paths:

- **`prod/` is still a git worktree, not a clone** — it shares `dev/.git` (one history), pinned detached at a
  release tag. `git worktree list` shows both dirs.
- **`store/` is still external to any checkout** — a *sibling* of `dev/` and `prod/`, not nested inside
  either, so no worktree/tag operation can touch the irreplaceable fossil record, and there is exactly one
  store. (The `.gitignore` `/store/` rule still holds for dev's throwaway `./store`.)
- **The scheduler still points at the worktree** — the installed plist's `WorkingDirectory` is
  `~/prospector/prod`, never the dev clone.

**`ops/deploy.sh`'s default is now `~/prospector/prod`** (`${PROSPECTOR_PROD:-$HOME/prospector/prod}`), so
`ops/deploy.sh <tag>` just works with no env var. `PROSPECTOR_PROD=…` still overrides for any other machine.

## Scope / what this is not

A path-convention refinement only. The worktree-not-clone choice, the external single store, the tag-only
deploy CONTRACT, the config-preservation behavior — all unchanged. Decision records are append-only, so
`2026-07-12-production-worktree-and-deploy.md` stays as written; this record supersedes its **example paths**
and nothing else.
