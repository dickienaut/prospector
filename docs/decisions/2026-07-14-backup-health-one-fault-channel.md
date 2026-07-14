# Backup health surfaces through ONE fault channel (fold → heartbeat), two triggers — and the checksum build is deferred

*Decision record, 2026-07-14. Ratifies the design-thread ruling on the **M7-02 / BK-3** backup-health
fork raised by the M6 deep review (`docs/notes/m6_deep_review_findings_qa.md`). Governing: spec §7 (store
durability), §8a (weekly heartbeat / dead-man), §10 (fault taxonomy). Extends
`docs/decisions/2026-07-12-store-durability-backup.md` (which first named bit-rot checksums as deferred
M7-hardening). **This record settles the design; it builds nothing** — the wiring lands later with the M7
heartbeat cluster.*

## Context — the fork

The M6 deep review raised two backup findings that look like one and are not:

- **M7-02 (HIGH judgment)** — `run.sh` runs `pros backup` as a **separate process after** the
  `pros run --heartbeat` that already sent the weekly email, and `backup_store` writes **no fault event**
  into the fossil store. So the heartbeat's `Health:` line (computed from the store's fault folds) can
  never reflect a backup failure. The operator whose *only* designed health channel is the weekly email
  sees "Health: OK" while the irreplaceable fossil record goes un-backed-up.
- **BK-3 (LOW judgment)** — the backup is fire-and-forget: no post-copy read-back/checksum, so a copy that
  *ran and reported success* but silently produced *bad bytes* is undetected.

The question posed to the design thread was: **where does backup health surface** — a fault the runner
folds, or a separate check the heartbeat reads? And: **do we build the checksum now?**

## The distinction the fork turns on

"**Did the backup run**" and "**is the backup good**" are two different facts that surface through the same
channel because they **fail differently**:

- *Did it run* is something the runner observes **in-band** — a backup that errors (unmounted drive, write
  failure, the loud faults the blessing marker already produces) is an **operational fault**, exactly like
  any other. No new mechanism is needed to *know* it; only a path to *emit* it.
- *Is it good* is the **corruption-in-the-safety-net** case: everything reports success and the bytes are
  wrong. It is detectable **only by a step that runs after the copy**, comparing source to target — it
  cannot live on the runner's happy path, because the whole point is catching the case where the copy
  *looked* fine.

## Decision 1 — ONE health channel: the fault fold the heartbeat already reads

Backup health surfaces as a **fault the runner folds**, which the heartbeat already carries as
OK/DEGRADED. We do **not** add a separate heartbeat-side backup check.

The runner already folds faults; the heartbeat already computes health off those folds. A backup fault —
*whichever* trigger fired it — flows through machinery that already exists. A **separate** heartbeat-side
backup check would be a **second health path parallel to the fault fold — a second source of truth for
"is the system healthy."** That is exactly the class of parallel mechanism this project keeps collapsing
into one (same family as the reading-list wall, the single `_emit_fault` accumulator, the one-scheduled-
entity wrapper). **The fault fold *is* the health channel; teach backup to speak through it.**

## Decision 2 — two triggers into that one channel

1. **"Didn't run"** → an **operational fault** (unmounted/unblessed drive, mid-copy write failure). This is
   the M7-02 gap: `backup_store` already records per-target failures in `report.failures` (and BK-1,
   PR #56, hardened the mid-copy case), but that lives in a separate `pros backup` process whose non-zero
   exit only reaches the launchd `StandardErrorPath` log. The fix is to route a backup failure into the
   **fault event the runner folds**, so the heartbeat carries it — no new health mechanism, just the
   emit-into-the-existing-fold path.
2. **"Ran but bad" (checksum mismatch)** → its own **`backup.integrity` fault**, emitted by the post-copy
   verification step (not by the copy operation reporting an error), with a **stable §10 suppression key**
   so a persisting mismatch pages once then rides the heartbeat. Same channel as (1), different trigger.

## Decision 3 — the checksum *build* is DEFERRED (lean: scheduled `verify-restore`)

The channel is settled now so Code does not invent a parallel mechanism. The **checksum itself is not
worth building yet**, and may never be built in that form:

- `rsync` already verifies size-and-mtime by default (and can checksum in-transit); the SQLite `.backup`
  API is transactionally consistent by construction; and **`pros store verify-restore` — already built —
  reindexes and reads a backup**, which is a *stronger* integrity proof than a checksum, just run
  on-demand rather than per-backup.
- The residual gap BK-3 names is therefore narrow: **silent bit-level corruption between per-backup runs,
  on the copy, that a periodic `verify-restore` would not catch in time.** Real but low-probability — which
  is why it is LOW, and a strong candidate for **named-and-deferred, earned when a real pain lands** (the
  same disposition as offsite/S3 and the WAL-checkpoint-out).

**The lean, recorded as the preferred version of BK-3:** schedule **`verify-restore` on a cadence** (e.g.
weekly) and let *that* be the integrity check, reusing a thing already built rather than adding a new one.
`verify-restore` proves the backup is **usable**, not merely **unchanged** — the fact actually worth
knowing. *A checksum tells you the bytes match; `verify-restore` tells you the backup would actually save
you.* The second is the real question.

## Guardrail — if the checksum path is built regardless

The integrity fault must be **loud and specific**: `backup.integrity`, with **the drive and the mismatched
path in the message**. A quiet "backup maybe corrupt" is worse than useless — it is the alarm layer
failing at its one job, on the one asset that is irreplaceable. Same standard as everything on the fault
layer: **if it fires, it says exactly what is wrong; if it cannot verify, it faults loud rather than
passing silent.**

## Scope / what did NOT change — and sequencing

- **Nothing is built by this record.** No change to `backup_store`, `run.sh`, the fold, the heartbeat, or
  any sensor. This settles the *shape* so the eventual build is unambiguous.
- **The M7-02 "didn't run → folded fault → heartbeat" wiring lands with the M7 heartbeat cluster**, not as
  a standalone patch: it shares the `run.sh`/runner/heartbeat territory with **M7-01** (heartbeat catch-up,
  still awaiting a separate design ruling) and **M7-03** (the unreachable OK/BROKEN line). Touching that
  territory once, together, avoids reworking it twice — and the finding itself noted M7-01/02/03 "compound
  into one operator blind spot; worth deciding together."
- **BK-1 + BK-2** (backup mid-copy failure recorded; mtime-window aliasing tiebreak) are the *separate*
  code slice in **PR #56** and are unaffected by this decision — they harden what `report.failures`
  contains; this decision governs where that failure *surfaces*.
