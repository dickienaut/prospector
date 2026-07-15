# backup-stale-health-channel — a failing backup is invisible to the operator's one health channel

*Bug record, 2026-07-14. Status: **fixed** — landed via #60. Class: §1.8 fails-silently (the severity frame; a
design-judgment gap, not a code defect). Tags: backup · heartbeat · email — Shape: fail-silent. The M6
deep-review **M7-02** finding; the first bug carried end-to-end under the §6 archive discipline (the dogfood).*

- **Symptom.** `ops/run.sh` runs `pros run [--heartbeat]` (which sends the weekly email) and THEN `pros backup`
  as a separate process. `backup_store` wrote **no fault event** into the fossil store — a backup failure
  surfaced only as a non-zero exit in the launchd `StandardErrorPath` log. So the weekly email's `Health:`
  line and recent-faults section (computed purely from store folds) could read **"OK" while backups had been
  failing for weeks.** The operator whose *only* designed health channel is that email (the weak, self-owned
  dead-man's whole premise is "read the email, not the logs") is blind to the one degradation that matters
  most — the irreplaceable fossil record going un-backed-up. Ordering compounded it: backup ran *after* the
  heartbeat, so even a same-tick failure couldn't reach that tick's email.

- **Root cause.** Not a code defect — a **structural gap.** Backup health had no path into the fault fold the
  heartbeat reads. `backup_store` records per-target failures in `report.failures`, but that lives in the
  `pros backup` process, whose only output is a CLI exit code + stdout; there was no mechanism for "is there a
  fresh successful backup on the drive" to become a fact the runner folds. (This is the M7-02/BK-3 fork the
  design thread untangled: *did it run* — observable in-band, an operational fault — vs *is it good* —
  corruption in the safety net, detectable only by a post-copy step. This record is the first; the second
  stays deferred.)

- **Fix.** Backup speaks through the **one channel that already exists** (decision 2026-07-14): the fault fold
  the §8a heartbeat carries as health — **not** a second heartbeat-side backup check (that would be a parallel
  source of truth for "is the system healthy," the exact class this project keeps collapsing into one). Two
  parts: **(1)** `pros backup` stamps a `.prospector-backup-ok` marker (the backup's UTC time) on each target
  **on verified success** — inside the per-target try, after the copy + registry land, so a mid-copy failure
  leaves no fresh marker (never on attempt, the `heartbeat.sent` discipline). **(2)** the runner reads each
  configured target's marker every tick (`_check_backup_freshness`, in the `finally` before `_compute_push`)
  and folds `backup.stale` if the marker is **missing** (never-backed-up / unmounted / lost) or **older than
  `backup.max_age_days`** (DEFAULT 3) — both the same actionable fact. Stable per-target
  `key=f"backup.stale:{target}"` so a persisting-stale drive pages once then rides the heartbeat; the message
  keeps the moving ts for forensics. Commit in #60. **Deferred (decision §3, BK-3):** the "ran but bad"
  checksum trigger — the lean is a scheduled `verify-restore` (proves the backup is *usable*, not merely
  *unchanged*), reusing a thing already built.

- **Regression test.** `tests/test_runner_backup_stale.py` (6) + `tests/test_backup.py` (3, marker
  write/skip/read). RED-first: the runner folds `backup.stale` on a **missing** and a **stale** marker (and
  pages), **not** on a **fresh** one, **not** on a 2-day marker (one slept-through cycle must not cry wolf),
  **not** with no targets configured; a **persisting** stale backup pages **once** then rides the heartbeat
  (the §10 suppression, keyed on the stable per-target key). RED verified by disabling the tick call — the
  stale fault vanishes and the assertion drops to `0 == 1`. The marker is stamped on a verified target,
  **absent** on one that failed mid-copy (BK-1's case), and absent when `now` is omitted.

- **Rule born.** None new — this **builds the mechanism a ratified decision specified**
  (`2026-07-14-backup-health-one-fault-channel.md`). Its value is the reinforcement: backup health, like the
  §10 sensor faults and the dead-man's liveness, flows through the **one `_emit_fault` accumulator + fault
  fold** — the recurring "collapse the parallel health path into the existing one" discipline (kin to the
  single `_emit_fault`, the one-scheduled-entity wrapper, the reading-list wall). The `backup.stale` fault
  inherited the E1/R4 stable-`key=` convention **for free** — a new fault site that got it right by
  construction (the convention propagating, not re-breaking).

- **References.** `notes/m6_deep_review_findings_qa.md` (M7-02, the finding + its compounding with BK-1 /
  M7-03), `docs/decisions/2026-07-14-backup-health-one-fault-channel.md` (the settled shape — one channel, two
  triggers, checksum deferred), `docs/notes/2026-07-14-m7-heartbeat-cluster-build-note.md` (Ruling 2 — the
  marker mechanism + the three guardrails). Sibling bugs by ID: M7-01 / M7-03 (#58, the heartbeat cluster this
  completes); BK-1 (#56, the mid-copy failure whose per-target `report.failures` this now surfaces); BK-3 (the
  deferred "ran but bad" sibling). Class kin (§1.8 fail-silent on the alarm layer): SNAP-01, the fault-taxonomy
  count-lie.
