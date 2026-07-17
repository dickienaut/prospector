# Activation checklist (the T.O.) — on-Mac autonomy, backups, and the dead-man

*The blank procedure. Each execution produces a dated completion record — the **781** — filed under
`docs/notes/YYYY-MM-DD-activation-781.md` as an append-only fossil: **observed values, never ticks.** This file
is **amended in place** when a slice adds an on-Mac item (the maintenance gate: a slice isn't done until its
on-Mac items are here — a stale checklist is worse than none). Design rationale:
`docs/notes/2026-07-15-activation-checklist-design-note.md`.*

## The three rules that make it worth running

1. **Observe, don't tick.** Every item wants an *observed value* — a run id, a path, a count, the email's text
   — not a checkmark. An action item can be checked off by someone who *meant* to do it; an observation can
   only be completed by looking at something.
2. **Two witnesses per critical item.** A single source can lie. The first run is the launchd log *and* a new
   run event in the store; the lock is `lock-path` identical from *both* checkouts.
3. **No-go gates block "armed."** The backup is not trusted until a restore has actually been performed; the
   dead-man is not armed until its silence has been proven to get noticed; capture does not arm until the live
   byte-compare passes. Advisory items inform; gates block.

## When to run it

- **Once at arming** — or to **audit an activation already performed** (the same items, observed after the
  fact; that is what the 2026-07-17 781 does).
- **Again** after a rebuild, a store migration, or a macOS upgrade.
- **A subset** (items 10–11, the deploy/lock items) after any deploy that touches `ops/`.

Not a daily ceremony.

---

## Part A — Base activation (the procedure)

Layout: `~/prospector/{dev, prod, store}`. **`prod`** is a git worktree pinned at a release **tag**, sharing
dev's `.git`; the **store** lives outside any checkout. The launchd job, `run.sh`, and `install.sh` all point
at `prod`, never the dev clone.

1. **Prod worktree + external store** (once, from `~/prospector/dev`):
   `git worktree add ~/prospector/prod <tag>` then `( cd ~/prospector/prod && uv sync )`.
   Machine-local **paths** go ONCE in the untracked, gitignored overlay
   `~/prospector/prod/config/prospector.local.yaml` (deep-merged over the tracked config; the config hash
   covers the merged result — **never hand-edit the tracked `config/prospector.yaml`**): `store.root`,
   `backup.targets`.
2. **Secrets** — `~/prospector/prod/.env` (git-ignored, per-checkout): `TIINGO_API_TOKEN` (**required** — the
   code reads `TIINGO_API_TOKEN`, not the spec's stale `TIINGO_API_KEY`), `PROSPECTOR_SMTP_PASSWORD`
   (**required** once `email.smtp_host` is set — `pros run` fails fast otherwise). `ANTHROPIC_API_KEY` only if
   arming capture (Part C).
3. **Bless the backup drives** (physical, once per drive): `touch /Volumes/<DRIVE>/prospector/.prospector-backup-target`.
   The marker is the operator's hand-made sentinel — the code **never** creates it, so an unplugged drive's
   vanished mount point means the marker is absent → the target **faults loud** instead of silently writing the
   "backup" onto the internal disk under `/Volumes`.
4. **Prove the backup before trusting it** — items 7–9 below.
5. **Install the schedule** — from `~/prospector/prod`, pick the LOCAL time equal to `schedule.daily_utc`
   (22:30 UTC): `./ops/install.sh <LOCAL_HOUR> <LOCAL_MINUTE>` (US-Eastern = `18 30`). Idempotent
   (`plutil -lint`, then `launchctl bootout` + `bootstrap` in `gui/$(id -u)`). `RunAtLoad=false` — installing
   is **not** a run-now surface.
6. **Keep the Mac awake** — disable system sleep or schedule `pmset` wakes (launchd's run-a-missed-job-on-wake
   is a backstop, not the primary mechanism).
7. **Calendar backstop** — a recurring reminder just after the weekly heartbeat window ("Prospector heartbeat —
   did it arrive?"). It lives **entirely outside git**; nothing here can confirm it (item 5, the purest one).

Operate / stop / ship:
- `launchctl print gui/$(id -u)/com.prospector.run` — status, next fire, last exit code, run count.
- `./ops/uninstall.sh` — stop (boots the agent out, removes the plist; never touches the store).
- `ops/deploy.sh <tag>` from the dev repo — ship a later release (tag-only, lock-coordinated checkout + `uv sync`).

---

## Part B — The verification set (11 base items; capture is Part C)

Fill the **observed** column in the **781**, not here. `GATE` = no-go: blank blocks "armed."

| # | Item | What to observe | Two witnesses | Gate? |
|---|------|-----------------|---------------|-------|
| 1 | First **unattended** scheduled run | run id + ts, no manual trigger | launchd `out.log` · a new `runs/` entry in the store | **GATE** |
| 2 | Mac stays awake | sleep disabled / wakes scheduled | `pmset -g` | advisory |
| 3 | Heartbeat arrives, legible | the `[PROS]` email reads OK/DEGRADED + last-run date | the email itself · the folded `heartbeat.sent` | **GATE** |
| 4 | Dead-man **human loop** | a suppressed cycle's missing heartbeat is *noticed* | the absence · the calendar reminder firing | **GATE** |
| 5 | Calendar backstop exists | recurring reminder, timed just after the heartbeat | the calendar itself (outside git) | **GATE** |
| 6 | Concurrent read | dashboard renders cleanly during a scheduled write | the dashboard · the run completing | advisory |
| 7 | HDD blessing markers | PRESENT on both targets | `.prospector-backup-target` on each drive | **GATE** |
| 8 | First backup | completes to both targets, `registry=ok`, no FAULT | exit status · files on the drives | **GATE** |
| 9 | `verify-restore` | reindex succeeds; counts match the live store, `skipped=0` | command output · spot-checked counts | **GATE** |
| 10 | `deploy.sh` refuses under a held lock | refuses loudly, nonzero (exit 4 / inner `lock-run` 75) | the refusal message · the next tick runs clean | **GATE** |
| 11 | Dual `lock-path` identity | identical path from dev and prod | `pros store lock-path` in each checkout | **GATE** |

Commands for the scriptable items (run from `~/prospector/prod` unless noted):
- **8 / 9** — `uv run pros backup` ; `uv run pros store verify-restore /Volumes/<DRIVE>/prospector` → compare
  the reported `events` / `snapshots` / `fund_objects` to `uv run pros lead list` and `uv run pros store reindex`.
- **10** — hold the lock in one shell (`uv run pros store lock-run -- sleep 60`) and run `ops/deploy.sh <tag>`
  from the dev repo in another → observe the refusal + `exit 4`.
- **11** — `uv run pros store lock-path` from `~/prospector/dev` **and** `~/prospector/prod` → assert identical.
  Closes DEPLOY-OVERLAY-DRIFT: `deploy.sh` locks from the *dev* checkout on the premise that both resolve
  `store.root` to the same external store; the overlay is per-checkout and untracked, so if it drifted a deploy
  would lock the wrong store and proceed during a live tick, silently. This is the one gap the mechanism cannot
  verify from inside itself.

---

## Part C — Capture (M6) arming — a SEPARATE, deferred sub-procedure

Capture **ships disabled** (`capture.monthly_budget_usd: null`). It is armed **later**, deliberately, **not** as
part of base activation. All three are no-go gates, and **item 14 cannot be proven in CI** — there is no armed
API in the test environment.

| # | Item | What to observe | Gate? |
|---|------|-----------------|-------|
| 12 | `ANTHROPIC_API_KEY` present | in both checkouts' `.env`; the fail-fast does NOT fire | **GATE** |
| 13 | Budget set | `capture.monthly_budget_usd` = value; `capture.unit_price_usd` verified vs the live price (CAP-USD, else the USD cap can never fire) | **GATE** |
| 14 | Armed byte-compare | one real armed call: `issued == query`, **byte-exact** (CAP-DRIFT) | **GATE** — capture arms only *after* this passes |

Ref: `docs/decisions/2026-07-14-query-drift-byte-exact.md`. If the live call shows benign cosmetic
normalization, that is a **finding** → a minimal, *named* normalization for that one source, documented — never
a blanket `.strip()`/case-fold.
