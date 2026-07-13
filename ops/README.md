# ops/ — the M7 autonomy core (scheduled runner)

*Makes the monitor **autonomous**: it runs itself on a schedule (launchd), backs up the fossil store after
each run, and the weekly heartbeat arms the §8a dead-man ("silence > 7 days = broken"). Design:
`docs/notes/2026-07-11-m7-autonomy-core-scheduling.md`; ratified in
`docs/decisions/2026-07-12-m7-autonomy-core.md`. These files are **inert until you run `install.sh` on the
Mini** — nothing here executes on its own.*

## What's here

| file | what it is |
|---|---|
| `run.sh` | The wrapper launchd invokes. `cd`s to the repo root, fixes `PATH` for `uv`, then runs `pros run` (with `--heartbeat` on Sundays) `&& pros backup`. The one debuggable script. |
| `com.prospector.run.plist` | The LaunchAgent **template** (`__PLACEHOLDERS__`). `install.sh` fills it in. |
| `install.sh` | Substitutes the template, validates it (`plutil -lint`), installs to `~/Library/LaunchAgents/`, and `launchctl bootstrap`s it. Idempotent. |
| `uninstall.sh` | `launchctl bootout` + removes the installed plist. |
| `deploy.sh` | Ship a release to the prod worktree: `ops/deploy.sh <tag>` (run from the dev repo). Tag-only; preserves machine config; `uv sync`s. |

## The deploy-from-tag shape — a git worktree, one store, one command

**The scheduler runs from a git *worktree* pinned at the release tag — one repo, two working dirs, never a
second clone and never your dev tree on `main`.** A worktree shares the dev repo's `.git` (one history), so
there is nothing to mistake for the dev clone; production is just a directory checked out at a frozen tag,
immune to your churn on `main`. Set it up once (from the dev repo):

```sh
# one-time: production as a worktree pinned at the tag, + the store OUTSIDE any checkout.
# Consolidated layout — ~/prospector/{dev,prod,store}: dev clone, prod worktree, store side by side
# (2026-07-12-consolidated-prospector-layout.md). Run from the dev clone (~/prospector/dev):
git worktree add ~/prospector/prod v1.0.1             # one repo — `git worktree list` shows both dirs
# then set machine-local config ONCE in ~/prospector/prod/config/prospector.yaml:
#   store.root: ~/prospector/store        # the ONE canonical store, sibling of the checkouts
#   backup.targets: [/Volumes/…, /Volumes/…]
( cd ~/prospector/prod && uv sync )
```

- **`store.root` points OUTSIDE the checkout** (`~/prospector/store`, a sibling of both checkouts), so no
  worktree/tag operation can ever touch the irreplaceable fossil record — and there is exactly ONE store (dev
  testing uses the dev clone's throwaway `./store`).
- The plist's `WorkingDirectory` and `run.sh` path point at the **worktree** (`~/prospector/prod`), **never**
  the dev clone — that pointer *is* the isolation; get it wrong and prod runs your dev tree.
- **Ship a later release with one command** (from the dev repo), so you never hand-navigate prod:
  ```sh
  ops/deploy.sh v1.0.2      # TAG-ONLY (refuses a branch/SHA); preserves your machine config; uv syncs
  ```
  `main` never touches production; the next scheduled run picks up the new code (no restart).

*Changelog: paths consolidated to `~/prospector/{dev,prod,store}` (was the scattered `~/prospector-prod` /
`~/prospector-store` example paths) — `docs/decisions/2026-07-12-consolidated-prospector-layout.md`.*

## Activation runbook (on the Mini)

1. **Production worktree** at the tag + external store (above). Everything below runs in `~/prospector/prod`.
2. **`.env`** in that directory — `TIINGO_API_TOKEN` and `PROSPECTOR_SMTP_PASSWORD` are required (the run
   fails fast without them); `edgar.user_agent` lives in `config/prospector.yaml`. `uv sync` once so the venv
   exists.
3. **Backups first** — attach + bless the two HDDs and set `backup.targets` per
   `docs/notes/2026-07-12-mac-backup-activation-checklist.md`. Until then `pros backup` (and so `run.sh`)
   **faults loudly** — by design, never a silent no-op.
4. **Install the schedule** — pick the **LOCAL** time equal to `schedule.daily_utc` (22:30 UTC, after US
   close). Example if the Mini is US-Eastern (UTC−4/−5): `18 30`.
   ```sh
   ./ops/install.sh 18 30      # <LOCAL_HOUR> <LOCAL_MINUTE>
   ```
5. **Keep the Mini awake** — it's a server. Disable system sleep (Energy settings) or schedule wakes with
   `pmset`. launchd's run-on-wake is then a backstop, not the primary mechanism.
6. **Calendar backstop** (the weak dead-man's human loop) — a recurring reminder just after the expected
   weekly heartbeat: *"Prospector heartbeat — did it arrive?"* Email there → dismiss; absent → investigate.
   This is what converts "hope I notice silence" into "a reminder makes me check."

## Acceptance — done when (prove it, don't assume)

- **It runs itself:** the scheduled fire lands with no manual trigger — confirm via the launchd log
  (`~/Library/Logs/com.prospector.run.{out,err}.log`) **and** a new `runs/` entry in the store.
- **The heartbeat is legible:** the weekly email arrives with explicit **health (OK / DEGRADED)** and the
  **last-run date**.
- **The dead-man's human loop works:** stop the agent for a cycle (`./ops/uninstall.sh`), confirm the
  heartbeat does *not* arrive when expected, and confirm you'd catch it (the calendar reminder / you notice).
  The M7 analog of "watch the CI gate actually block." Re-install after.
- **Concurrent read:** the dashboard reads cleanly while a scheduled run writes (WAL mode — a verification).

## Operate

```sh
launchctl print gui/$(id -u)/com.prospector.run     # status / next fire / last exit code
launchctl kickstart -k gui/$(id -u)/com.prospector.run   # force a run now (debugging only — not a cadence surface)
./ops/uninstall.sh                                   # stop it
```

**Deferred (M7-hardening, not this slice):** infra-as-code provisioning of the Mini, WAL-checkpoint-out for
read-only-media serving, offsite backup (S3/Backblaze), the SOI cadence gate. They land when a real pain
earns them.
