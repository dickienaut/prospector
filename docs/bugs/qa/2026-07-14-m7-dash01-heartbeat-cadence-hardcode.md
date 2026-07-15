# M7-DASH-01 — dashboard dead-man ignores the configured heartbeat cadence

**Severity:** MED (nuisance-alarm / GPWS class — introduced by PR #58's M7-03 fix)
**Verdict:** NEW / CONFIRMED on real substrate
**Files:** `prospector/dashboard/app.py:81`, `prospector/dashboard/export.py:197`
**Correct pattern to mirror:** `prospector/runner/email_render.py:58-59`
**Broken promise:** `config/prospector.yaml:389-393` ("one clock, one source")

## What
Both dashboard surfaces hardcode the dead-man silence floor to 7 days and ignore
`schedule.heartbeat_cadence_days`, which the runner send-gate and the email floor both honor.
- cadence > 7 → healthy system reads BROKEN (cry-wolf on the dead-man).
- cadence < 7 → dashboard reads OK while the channel is overdue (false-negative — worse).

The suite misses it because every test pins cadence == 7 (green-on-synthetic).

## Deliverables in this branch (Option 2 — QA proposes, implementer applies)
- **RED-first tests:** `tests/test_dashboard_heartbeat_cadence.py` — two `@pytest.mark.xfail(strict=True)`
  tests that drive the REAL call sites (`AppTest` for app.py, `board_snapshot_markdown` for export),
  not `views.heartbeat` with a floor computed inside the test (which would pass for the wrong reason).
  - RED against `main` @ 74a4394: **2 xfailed** (bug reproduced through the real paths).
  - GREEN against the reference fix: **2 XPASS(strict)** (fix closes both).
- **Reference fix:** `docs/notes/m7_dash01_fix.diff` — 2 source files, `git apply --check` clean against
  74a4394; each a one-line thread of `cfg.schedule.heartbeat_cadence_days` (both callers already hold cfg).

## Implementer handoff (xfail-strict protocol)
Apply `m7_dash01_fix.diff`, then remove the two `xfail(strict=True)` markers from the test file — they
flip to XPASS(strict) (= "failed") until removed, which is the signal the fix landed. Full suite stays
609 passed / 1 skipped / 2 xfailed after removal.

## Companion (fold into the same pass)
- **HB-NOTE-01 (LOW):** `email_render.py:253` hardcodes "7-day floor" in the heartbeat footer regardless
  of cadence — same one-clock drift, cosmetic. Not patched here; trivial one-liner.

See `docs/notes/2026-07-14-post-m6-stack-review_qa.md` for the full review (all 7 confirmed-closed fixes
+ the 5 new findings + reproductions).
