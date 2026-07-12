# M7 autonomy core — scheduled runner + the (weak) dead-man

*Decision record, 2026-07-12. Ratifies and records the build of the **M7 autonomy core**: the monitor now
runs itself on a schedule (launchd), backs up the fossil store after each run, and the weekly heartbeat
**arms the §8a dead-man** ("silence > 7 days = broken"). Implements the design note
`docs/notes/2026-07-11-m7-autonomy-core-scheduling.md`; the code is the `ops/` scaffolding + a heartbeat-email
health line. This is the M7 **core**, not the full M7 hardening (§ Deferred). After this ships and is
activated on the Mini, **v1 is build-complete.***

## What was built (this PR)

- **`ops/run.sh`** — the wrapper launchd invokes. `cd`s to the repo root and fixes `PATH` (launchd's minimal
  env has no profile → the classic "`uv` not found / `.env` not found" failures), then runs
  `pros run [--heartbeat] && pros backup`. This is where the **backup cadence** is wired (deliberately not
  inside `pros run` — the store-durability decision).
- **`ops/com.prospector.run.plist`** (template) + **`ops/install.sh` / `ops/uninstall.sh`** — one LaunchAgent,
  `StartCalendarInterval` once daily, `StandardOut/ErrPath` logging; installer substitutes paths/time,
  `plutil -lint`-validates, and `launchctl bootstrap`s idempotently.
- **`ops/README.md`** — the on-Mini activation runbook.
- **Heartbeat email health line** (`prospector/runner/email_render.py`) — an explicit **OK / DEGRADED** health
  (DEGRADED = an operational fault fired this cycle), reusing the view-models the render already imports.
- **Nothing else executes.** The `ops/` files are inert until `install.sh` runs on the Mini — the PR's blast
  radius is essentially zero until activation.

## The load-bearing decisions

- **launchd, not cron.** cron silently skips a job if the Mac was asleep at the scheduled time; launchd runs a
  missed `StartCalendarInterval` job when the machine wakes. For a Mini that may sleep, that's the difference
  between "ran late" and "silently didn't — and the dead-man now has to catch it."
- **One plist, the wrapper decides heartbeat day — for dead-man semantics, not just fewer parts.** With ONE
  scheduled entity, if it fires everything fires and if it dies everything dies, so a **missing weekly
  heartbeat unambiguously attests "the runner is dead."** Two plists (a daily + a separate weekly) make
  heartbeat-delivery and daily-running *independently failing* — the Sunday plist could break alone, killing
  the heartbeat while daily runs continue, and silence would no longer mean "runner dead," only "one of two
  plists broke." That is ambiguity injected into the one channel whose entire job is unambiguous absence. So
  the day-decision lives in `run.sh` (`date +%u == 7` → `--heartbeat`), a versionable, testable shell
  conditional rather than fiddly plist weekday XML. It **duplicates** config `schedule.weekly_day` (the flag
  design makes the day external either way) — a `# keep in sync with weekly_day` comment guards the drift.
- **OK / DEGRADED health — the §10 summary-honesty rule.** Today's `Heartbeat: OK` attests only "the email
  sent"; a reader reads it as "the system is healthy," so on a faulting cycle it lies by connotation. The same
  standard that governed the whole §10 arc (the summary must match what fired) now applies to the heartbeat's
  own line: DEGRADED the moment an operational fault fires. Liveness (the silence dead-man, `hb["ok"]`) is the
  separate axis and rides alongside. A review-advisory alone is a correct punt, not breakage → stays OK.
- **Deploy from the `v1.0.0` tag, via a SEPARATE production checkout.** The scheduled runner deploys from the
  tag, not `main` HEAD (`2026-07-11-ci-and-branch-protection.md`). Concretely: a production clone
  (`~/prospector-prod`) pinned at `v1.0.0`, with the plist's `WorkingDirectory` pointing there — **never the
  dev clone on `main`**, so dev churn can't touch what the scheduler runs. Naming the second clone (not just
  "checkout the tag") is the load-bearing detail; the runbook does.
- **The weak, self-owned dead-man.** No external healthcheck (nothing to change pricing, break its API, or fold
  over a 20-year horizon): the heartbeat email carries health + last-run, and a **self-owned recurring calendar
  reminder** ("did the heartbeat arrive?") is the human backstop. **Honest residual (accepted):** if the Mac
  dies *and* you're away *and* you miss the reminder, the dead-man doesn't fire — the accepted limit of the
  dependency-free version; a strong external healthcheck is the upgrade if that residual ever bites.
- **Concurrent read is a verification, not new code.** WAL mode already allows one writer + concurrent readers,
  so the dashboard reads cleanly during a scheduled write. (The WAL-checkpoint-out for read-only *media* is a
  different, deferred concern — do not conflate.)

## Posture honored

`pros run` and `pros backup` remain the only cadence-driven surfaces — no run-now button is added (the
LaunchAgent is the only thing that fires runs). The heartbeat rides an actual run (`pros run --heartbeat`), so
a received email proves the whole pipeline ran. This PR lands via branch → green CI → PR → owner review
(never a Code self-merge), and the scheduler ultimately deploys from the reviewed, tagged release.

## What remains (owner, on the Mini — not code)

Install the LaunchAgent (`ops/install.sh <local HH> <MM>` = local equivalent of `schedule.daily_utc` 22:30
UTC), keep the Mini awake (`pmset` / Energy settings), set the calendar backstop, **bless the backup HDDs**
(`docs/notes/2026-07-12-mac-backup-activation-checklist.md`), then run the acceptance tests in `ops/README.md`
(it fires itself · the heartbeat is legible · the dead-man's human loop works · the dashboard reads during a
write), and cut `v1.0.0`.

## Deferred — M7-hardening (named, not the core)

Infra-as-code / reproducible provisioning of the Mini; WAL-checkpoint-out for read-only-media serving; offsite
backup (S3 / Backblaze — the dormant `store/s3_sync.py` + `s3.bucket`); the SOI-corroboration cadence gate
(N9). Each lands when a real pain earns it.
