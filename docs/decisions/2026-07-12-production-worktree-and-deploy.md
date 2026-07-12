# Production is a git worktree, not a second clone; deploys are one tag-only command

*Decision record, 2026-07-12. Refines the M7 deploy-from-tag shape (`2026-07-11-ci-and-branch-protection.md`
§Deferred; `2026-07-12-m7-autonomy-core.md`) after activating v1 on the Mac mini exposed an ergonomic footgun.
Amends `ops/README.md`'s "deploy-from-tag shape" section (separate clone → worktree). Design thread
concurring.*

## The problem it fixes

Deploy-from-tag was first implemented as a **second full clone** (`~/prospector-prod` @ tag) beside the dev
clone (@ `main`). The owner immediately hit the failure it invites: **edited the dev clone, ran production,
and couldn't tell why nothing changed** — two near-identical repos that must never be confused. Plus the store
had been migrated *into* the clone, leaving **two stores** ("which is live?"). The isolation was real but rested
on *remembering which directory is which, every time, for the life of the system* — discipline-by-vigilance,
the weak form this project keeps replacing with mechanism (the branch-protection ruleset, the never-execute
wall). Two clones is the vigilance version of deploy-from-tag.

## The decision

**Production is a git `worktree`, not a clone.** One repository (`~/Documents/coding/prospector`), two working
directories sharing one `.git`: dev on `main`, and `~/prospector-prod` a worktree pinned (detached) at the
release tag. This gives the *exact* release-isolation — production runs frozen, tagged code, immune to churn on
`main` — with **no second clone to mistake for the first.** The confusion isn't managed with a banner; it stops
existing, because there is only one repo. `git worktree` is the one genuine concept being adopted; its cost is
paid once, versus the confusion cost of two clones paid on every deploy.

Two supporting choices, both **mechanism-over-memory:**

- **One store, external** — `store.root: ~/prospector-store`, *outside* any checkout, so no worktree/tag/clone
  operation can ever touch the irreplaceable fossil record, and there is exactly one canonical store. The dev
  clone's `./store` is deleted; dev testing uses a throwaway. (Resolves the two-stores ambiguity structurally.)
- **`ops/deploy.sh <tag>` is the one deploy command**, run from the dev repo — so the owner almost never
  hand-navigates prod. It enforces the CONTRACT rather than relying on care:
  - **Tag-only.** It refuses any ref that isn't a tag (a bare branch or SHA is rejected via
    `refs/tags/<tag>^{commit}`), so production can never be silently pinned to a *moving* ref — deploy-from-tag
    made structural.
  - **Config-preserving.** Machine-local config (`store.root`, `backup.targets`) lives in the tracked
    `config/prospector.yaml`; deploy.sh stashes it across the checkout and re-applies it, and **stops loudly**
    if a release changed that file upstream (reconcile deliberately — never a silent machine-config wipe).

The **plist's `WorkingDirectory` points at the worktree**, never the dev clone — that pointer *is* the
isolation; getting it wrong runs production on the dev tree.

## Flagged for the design thread (not built here)

Machine config in the *tracked* `config/prospector.yaml` is the awkward seam; deploy.sh's stash/re-apply is a
pragmatic patch. The clean answer is an **untracked `config/prospector.local.yaml` overlay** merged over the
tracked config, so machine settings live in a file no checkout touches and deploy.sh needs no config
gymnastics. It is deferred because it changes config *loading* and must fold into the **config-hash / config
honesty CONTRACT** (the `config.changed` fossil must hash the *effective merged* config) — a design-thread call,
not an implementation one.

## Scope / what this is not

A deployment-topology refinement. It does not change the runner, the store format, the firewall, or the
deploy-from-tag CONTRACT itself (production still deploys from a tag — this makes the mechanism match the
intent). `git worktree remove` + a fresh `git worktree add` is always a clean reset since the store lives
outside the worktree.
