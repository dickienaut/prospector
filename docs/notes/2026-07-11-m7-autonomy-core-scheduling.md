# M7 autonomy core — scheduling + the (weak) dead-man: build note (2026-07-11)

*Build note for Claude Code. Makes the monitor **autonomous**: it runs itself on a schedule, a missed run is
noticeable, and the dashboard reads cleanly while a scheduled run writes. This is the M7 **core** — the
autonomy-delivering, dead-man-arming slice — **not** the full M7 hardening (infra-as-code, reproducible
provisioning, read-only-media serving, offsite backup), which stays deferred (§5). Dead-man design decided by
the operator: **the weak version** (self-owned, no external dependency — reasoning in the design thread).
Governing: spec §9 (runner/ops), §10 (heartbeat/dead-man). Pairs with the store-backup note (the schedule
runs `pros run` then `pros backup`). **Read the real `email_render.py` heartbeat block and the store's WAL
config first.**

## 1. launchd scheduling — NOT cron

Schedule `pros run` via a macOS **LaunchAgent**, not cron. The reason is load-bearing: **cron silently skips a
job if the Mac was asleep at the scheduled time** (the run just doesn't happen, no error); **launchd runs a
missed `StartCalendarInterval` job when the machine wakes.** For a Mini that may sleep, that's the difference
between "it ran late" and "it silently didn't, and the dead-man now has to catch it."

- **Plist:** `~/Library/LaunchAgents/com.prospector.run.plist`, `StartCalendarInterval` at chosen clock times
  (the runner is EOD-oriented — pick a time after US market close, e.g. once daily post-close; twice daily if
  the cadence wants it).
- **Call a wrapper script, not `uv run pros run` directly.** launchd runs with a minimal environment and does
  **not** source your shell profile — the classic gotchas are PATH (`uv` not found) and working directory
  (`.env` not found → no Tiingo token). A wrapper (`ops/run.sh`) that: `cd`s to the repo root (so `.env`
  resolves), sets `PATH` to include `uv`'s location (or calls `uv` by absolute path), then runs
  `uv run pros run && uv run pros backup`. One debuggable script; launchd just invokes it.
- **Logging:** set `StandardOutPath` / `StandardErrorPath` in the plist to a log file. The run's *own* faults
  go to the store and the email; the launchd log catches the catastrophic **"didn't even start"** failures
  (uv missing, `.env` gone) that never reach the app.
- **Install:** `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.prospector.run.plist` (modern) or
  `launchctl load` (older). **And keep the Mini awake** — it's a server: disable sleep (Energy settings) or
  schedule wakes via `pmset`. Simplest: don't let the server sleep; then launchd's wake-behavior is a backstop,
  not the primary mechanism.

## 2. Arm the dead-man — the weak version (decided)

The heartbeat now fires on a real cadence, so **a missing heartbeat = a missed run = something is broken**, and
the operator — who expects the weekly heartbeat and has local awareness of the Mini — investigates its absence.
Two pieces make this reliable without any external dependency:

- **[email change] Put explicit health in the heartbeat email.** It already carries "Heartbeat: OK · last run
  {date}"; surface the *health state* — **OK / DEGRADED** (faults present this cycle) — and the **last-run
  date prominently**, computed from the same folds the dashboard's heartbeat indicator reads (reuse that
  view-model; don't recompute). So a *received* email says not just "it ran" but "it ran and is
  healthy/degraded" at a glance; an *absent* email says "it stopped — go look."
- **[operator setup, zero-dependency] A self-owned calendar backstop.** The one weakness of the weak version is
  that humans don't notice things that *don't arrive*. Fix it without a third-party healthcheck: a **recurring
  calendar reminder** (your own Google Calendar, since you're on Workspace) timed just after the expected
  weekly heartbeat — *"Prospector heartbeat — did it arrive?"* Email there → dismiss; absent → investigate.
  This converts "hope I notice the silence" into "a reminder makes me check," and it's **self-owned** — no
  external service to change pricing, break its API, or fold over a 20-year horizon (the reason the weak
  version was chosen over an external healthcheck).

**Honest residual (documented, accepted):** if the Mac dies *and* you're away *and* you miss the calendar
reminder, the dead-man doesn't fire. That's the accepted limit of the weak, dependency-free version — fine for
a personal system where the operator has local awareness. A strong external healthcheck remains the upgrade if
that residual ever bites.

## 3. Concurrent read — dashboard reading during a scheduled write

SQLite **WAL mode** already allows concurrent readers plus one writer, so the dashboard reads cleanly while a
scheduled `pros run` writes. **Confirm WAL is on** (it is, per the store design) — this is a verification, not
new code. (The **WAL-checkpoint-out** for serving the store from read-only *media* is a different concern —
deploying the store read-only — and it's M7-**hardening**, deferred; do not conflate it with this.)

## 4. Deferred — M7-hardening, named (NOT the autonomy core)

- Infra-as-code / reproducible provisioning of the Mini.
- WAL-checkpoint-out for read-only-media serving.
- Offsite backup (S3 / Backblaze) — per the store-backup note.
- The SOI-corroboration **cadence gate** (N9, the `xfail(strict)` that flips to XPASS when it lands).

The autonomy core is **scheduling + the weak dead-man + the concurrent-read check** — the hardening lands when
a real pain earns it.

## 5. Verify (done when)

- **It runs itself:** the scheduled run fires at the chosen time with no manual trigger — confirm via the
  launchd log *and* a new run in the store, on its own.
- **The heartbeat is legible:** an email arrives on schedule with explicit health (OK/DEGRADED + last-run date).
- **The backstop is set:** the recurring calendar reminder exists (if adopting it).
- **The dead-man's human loop works — prove it, don't assume:** stop the LaunchAgent for a cycle, confirm the
  heartbeat does **not** arrive when expected, and confirm you'd catch it (the calendar reminder fires / you
  notice the absence). The M7 analog of Phase 3's "watch the gate actually block."
- **Concurrent read:** the dashboard reads cleanly while a scheduled run writes.

After this, v1 is **build-complete** — both spawners live, the sender honest, the record backed up, and the
monitor running itself. What remains is M6 (discourse capture, front-loaded for v2) and the long run.
