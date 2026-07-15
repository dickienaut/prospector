# Prospector QA — Cold Review of the Post-M6 PR Stack

**Reviewed:** `main` as of 2026-07-14, commit `74a4394c6d5c` (the code of record, fetched via the authenticated tarball — not the local working tree, not the state-of-project doc).
**Baseline suite:** 609 passed, 1 skipped, 2 xfailed (env `prospector`, py3.12, `PYTHONPATH=.`, repo-root CWD). The 2 residual xfails are pre-existing deferred findings (SOI corroboration cadence), unrelated to this stack.
**Scope:** everything landed since the M6 merge (`0cb3227` → `74a4394`): **20 commits, 35 files, 8 source modules**. Prioritised the three PRs that fix findings I raised in the M6 deep review, since a wrong fix to a real bug is more dangerous than the bug.

**Method note.** A green suite is *not* the evidence here — over synthetic fixtures it is this project's signature false-pass. Every verdict below is backed by a reproduction driving the **real** code path over a **recorded-real or runner-faithful** substrate (the real TEKX SPDR holdings file; a real on-disk `EventStore`/`Registry`; the real Streamlit render via `AppTest`; the real backup loop over real files on one filesystem).

---

## Verdict summary

| PR | Finding | Verdict |
|----|---------|---------|
| #55 | **SNAP-01** (HIGH) snapshot-divergence fault bypassed the accumulator | **CONFIRMED-CLOSED** |
| #55 | **R1** (HIGH) cash-line CUSIP → spurious rebalance | **CONFIRMED-CLOSED** |
| #55 | **R4** (MED) prior-parse fault paged daily (volatile message) | **CONFIRMED-CLOSED** |
| #56 | **BK-1** (HIGH) blessed drive fails mid-copy → healthy drive skipped, no fault | **CONFIRMED-CLOSED** |
| #56 | **BK-2** (MED) mtime-window aliasing | **CONFIRMED-CLOSED** (correctness) |
| #58 | **M7-01** (HIGH) missed-Sunday heartbeat silently dropped | **CONFIRMED-CLOSED** |
| #58 | **M7-03** (MED) in-email Heartbeat line structurally always OK | **CONFIRMED-CLOSED** |

**All seven landed fixes verified correct on real substrate.** The stack is sound. But the cold read surfaced **five new findings** — one of them a MED nuisance-alarm the M7-03 fix *introduced* on the very alarm layer it was meant to harden.

## New findings

| ID | Sev | Subsystem | One-line | Actionable now |
|----|-----|-----------|----------|----------------|
| **M7-DASH-01** | **MED** | dashboard/export | dead-man silence floor hardcoded to 7, ignores configured `heartbeat_cadence_days` → cry-wolf (cadence>7) or false-negative (cadence<7) | **Yes — test + patch below** |
| BK-READ-01 | LOW | store/backup | BK-2 content-verify re-reads every unchanged rewritten-in-place file on every run (dst-HDD read amplification, unbounded as `ingest/` grows) | Decision-dependent |
| HB-NOTE-01 | LOW | email_render | heartbeat email footer hardcodes "7-day floor" regardless of cadence (same one-clock drift, cosmetic) | Yes (trivial) |
| M7-DOC-01 | LOW | runner | stale docstring cites retired `schedule.weekly_day` key | Yes (trivial) |
| BK-MSG-01 | INFO | store/backup | broad `except Exception` labels any fault "retry once the drive is healthy" (mislabels code bugs) | Note for M7-02 |

---

## CONFIRMED-CLOSED — the seven fixes (evidence)

### SNAP-01 (HIGH) — PR #55 · CONFIRMED-CLOSED
`_materialize_snapshots` (runner.py:1207-1218) now wraps the divergence sink in a `_snapshot_fault_sink` closure that routes through `_emit_fault` instead of the raw `store.append`. Grep confirms the **only** `store.append({"type":"fault"})` left in runner.py is *inside* `_emit_fault` (line 133) — no raw bypass remains on the snapshot path.

**Real-seam reproduction** (driving the actual `_materialize_snapshots` over a shadow dispersion lead with a divergent snapshot at `(lead, NOW)`): the divergence now lands in the `faults` accumulator = 1 (was 0), `_compute_push(...)` = **True** (was False), the store fault event is still written, and the snapshot row is still indexed afterward. The de-xfailed `test_snapshot_divergence_accumulator.py` drives this exact seam and is now a real green guard (asserts accumulator + push, not implementation).

*GPWS check:* the fault is keyless with a ts-bearing message, but this is **not** an R4-class daily nuisance — in normal forward-clock operation each tick writes a unique `(lead, now)` path (verified: two forward ticks → 0 divergences); it recurs only on same-timestamp reindex/replay, where the ts is fixed per occurrence → identical signature → suppressed after the first page.

### R1 (HIGH) — PR #55 · CONFIRMED-CLOSED
The fix excludes cash/derivative rows on the explicit `-` **ticker sentinel** (+ `MONEY MARKET` name), **not** via `priceable_members` — so it does not fall into the R2 trap of dropping foreign equities.

**Real-data reproduction** (the recorded TEKX SPDR file, whose two cash lines carry real CUSIPs `924QSGII3`, `999EURZ94`): a pure money-market sweep now accretes **no** rebalance, while a genuine constituent restructuring (including a foreign equity like Siemens Energy) *is* still caught. The de-xfailed `test_runner_rebalance_cash_and_prior.py` is a real green guard.

### R4 (MED) — PR #55 · CONFIRMED-CLOSED
The rebalance prior-parse fault now passes a stable `key=`, so two ticks a day apart with an unparseable prior produce an identical `_fault_signature` → suppressed after the first page (was paging daily on the moving prior date).

### BK-1 (HIGH) — PR #56 · CONFIRMED-CLOSED
The `backup_store` loop now wraps each target in per-target exception handling: a blessed drive failing mid-copy (ENOSPC / unplug) is **recorded as a failure** and the **healthy drive still completes** — no silent skip, no raw traceback. **Reproduction:** monkeypatching the copy to raise `OSError` partway through the blessed target leaves the second drive fully backed up and the failure surfaced as a non-zero-exit fault (was: healthy drive skipped, no failure recorded).

### BK-2 (MED) — PR #56 · CONFIRMED-CLOSED (correctness)
The mtime-window aliasing that could skip a changed file is closed by a content-verify fallback. Correctness intact — but see **BK-READ-01** below for a cost regression the same fix introduced.

### M7-01 (HIGH) — PR #58 · CONFIRMED-CLOSED
This was the decision-dependent finding (shipped as `xfail(strict)`, not a patch). Code made the design call: a `heartbeat.sent` event is now the single "last heartbeat sent" fact in the append-only `_system` stream; the runner reads it to compute whether the dead-man is due/overdue and **catches up** a cycle it slept through. **Reproduction** (real on-disk `EventStore`): simulating a missed Sunday then a Monday run now fires the catch-up (was: the week's dead-man signal silently dropped). The rewritten `test_runner_heartbeat_catchup.py` is a real green guard (my xfail contract flipped to a real pass).

### M7-03 (MED) — PR #58 · CONFIRMED-CLOSED
The in-email "Heartbeat: OK/BROKEN" line was structurally always OK (the current run synthesised as newest → silence 0). The fix keys liveness off `last_heartbeat_sent` (not last run), so the BROKEN branch is now genuinely reachable. **But the relocation introduced M7-DASH-01** — see below.

---

## M7-DASH-01 (MED) — the fix introduced a dead-man nuisance-alarm · NEW

**`prospector/dashboard/app.py:81` (hardcoded `floor_days=7`) and `prospector/dashboard/export.py:197` (no `floor_days` arg → default 7).** Correct pattern at `prospector/runner/email_render.py:58-59`; the broken promise at `config/prospector.yaml:389-393`.

PR #58's M7-03 fix relocated the OK/BROKEN dead-man liveness onto the dashboard and the board-snapshot export. Both surfaces **hardcode the silence floor to 7 days** and ignore `schedule.heartbeat_cadence_days` — the value the runner send-gate and the email floor both honor. The config comment is explicit that this key *"Feeds both the send cadence and the §8a silence floor (one clock, one source)."* The dashboard breaks that one-source promise, and both directions are dangerous:

- **cadence > 7 (e.g. fortnightly 14):** a HEALTHY, not-yet-due system reads **BROKEN** on the dashboard and in the exported board snapshot → **cry-wolf** on the dead-man (the GPWS class — the operator learns to ignore it).
- **cadence < 7 (e.g. 3):** the dashboard reads **OK** while the runner itself considers the channel **overdue** → a **false-NEGATIVE dead-man**, the more dangerous direction (an alarm that under-reports silence).

**Why the green suite misses it:** every existing test pins `cadence == 7`, so the hardcode exactly matches the default. This is the project's signature green-on-synthetic pattern — now landed on the very alarm layer the M7 fix was meant to harden.

**Reproduction** (real on-disk `EventStore`, last heartbeat 8 days before now, `AppTest` + the real `board_snapshot_markdown`):

```
silence=8d, configured cadence=14d (HEALTHY: next send at 14d)
  DASHBOARD floor=7 (app.py:81)      : ok=False  reason="silence 8d > 7d floor — broken"
  EMAIL/RUNNER floor=14 (cfg)        : ok=True   reason=None
  => CRY-WOLF: dashboard BROKEN on a healthy system
  board_snapshot_markdown(cfg cadence=14) prints: "- **heartbeat**: BROKEN — silence 8d > 7d floor"

silence=5d, configured cadence=3d (runner considers OVERDUE)
  DASHBOARD floor=7                  : ok=True
  RUNNER floor=3                     : ok=False  catch_up=True
  => FALSE-NEGATIVE: dashboard OK while channel overdue
```

**Fix (surgical, 2 lines):** thread `cfg.schedule.heartbeat_cadence_days` into both callers — both already hold `cfg` in scope, mirroring `email_render.py:58`. Reference patch `m7_dash01_fix.diff` (`git apply --check` clean against `74a4394`) and RED-first tests `test_dashboard_heartbeat_cadence.py` are in this branch. The two tests drive the **real** call sites (`AppTest` for app.py, `board_snapshot_markdown` for export) — deliberately *not* `views.heartbeat` with a floor computed inside the test, which would pass for the wrong reason.

---

## Lower-severity new findings

### BK-READ-01 (LOW) — BK-2 introduced dst-HDD read amplification · NEW
**`prospector/store/backup.py` — `_needs_copy` content-verify branch (~line 138) + `backup_store:205-207`.** The BK-2 content-verify re-reads **every unchanged rewritten-in-place file** (ingest / baselines / registry) on **every run** — a full dual read of source *and* destination HDD. Because `shutil.copy2` preserves source mtime, an unchanged file's dst mtime lands at delta ≈ 0, always inside `_MTIME_WINDOW_S` (2.0s), so the cheap size+mtime skip never triggers for these trees and control always falls through to `_same_bytes`. **Reproduced** (real TEKX xlsx × 3 + registry JSON, store unchanged between runs, same filesystem): run 2 with nothing changed → `files_copied=0` (correct) but 4 files fully dual-read (62,333 src bytes ×2); run 3 → the same 4 reads again. Not exFAT-specific. `ingest/` is the daily-accreting substrate, so the module's own comment that verify cost is "bounded to the small rewritten-in-place subset" erodes as it grows. **Correctness of BK-2 is intact — only its cost is unbounded over time.** The suite is blind because every backup test asserts copy/skip *counts*, never read volume (same green-on-synthetic root as M7-DASH-01, one layer down). Cheapest mitigation without losing BK-2: persist a content hash rather than re-reading both sides each run.

### HB-NOTE-01 (LOW) — heartbeat email footer hardcodes "7-day floor" · NEW
**`prospector/runner/email_render.py:253`.** The trailing note reads "silence beyond the 7-day floor means broken" regardless of the configured cadence, so a box tuned to a non-7 cadence emails a self-contradictory note (body says "CATCH-UP … > 14d cadence"; footer still says "7-day floor"). Text-only, no alarm decision keys on it — but the same one-clock drift as M7-DASH-01. Worth fixing in the same pass.

### M7-DOC-01 (LOW) — stale docstring cites retired config key · NEW
**`prospector/runner/runner.py:1123` (and a comment at :279).** #58 removed `schedule.weekly_day` from config and retired the local-weekday gate, but a SOI-corroboration docstring still cites `schedule.weekly_day` as a live reserved key. Documentation-only doc-drift breadcrumb pointing at config that no longer exists. (M7-05 sweep incomplete.)

### BK-MSG-01 (INFO) — drive-health text emitted for any exception · NEW
**`prospector/store/backup.py:210-213`.** The broad `except Exception` labels *every* fault "retry once the drive is healthy", so a non-drive code fault (KeyError/TypeError in the copy path) is mislabeled as a drive-health issue. Control flow is still correct (a genuine code bug hits both drives → both recorded → non-zero exit, never a silent skip), so this is a diagnostic-text nit. Flagged so the pending M7-02 work (backup health → heartbeat) doesn't propagate the misleading guidance for programming errors.

---

## Recorded for belief-state completeness (not a defect)

**R1 name-branch breadth** — `_is_cash_or_derivative` returns True for any row whose name contains "MONEY MARKET" regardless of ticker, so a hypothetical *real equity* named "…MONEY MARKET…" with a real ticker would be over-excluded. On the real TEKX file this branch is redundant (both cash lines already match the `-` sentinel) and no real instance of such a named equity exists (those names are cash vehicles). Not reproduced, not a blocker — recorded only so the belief-state is complete.

---

## What I recommend

1. **M7-DASH-01 is ready to land** — RED-first tests + a `git apply`-clean reference patch are in this branch (Option-2 composition: I propose, the implementer applies the `.diff` and removes the xfail markers). Fixing HB-NOTE-01 in the same pass closes the one-clock drift on both surfaces at once.
2. **BK-READ-01 is decision-dependent** — the fix (hash vs re-read) is a design call, so it's recorded but not patched. Flag it for the design thread; it pairs naturally with any M7-02 backup-health work.
3. **M7-DOC-01 / BK-MSG-01** — trivial/text; fold into the next docs sweep.

The headline stays: **the post-M6 stack is sound — all seven landed fixes verified correct on real data.** The one new alarm-layer regression (M7-DASH-01) is caught before it can train the operator to ignore the dead-man, which is exactly the failure mode this review exists to prevent.
