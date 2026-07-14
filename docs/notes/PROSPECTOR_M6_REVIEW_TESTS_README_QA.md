# M6 deep-review regression tests — SNAP-01, R1, R4, M7-01

Branch of record: `m6-discourse-capture` @ `4739b528bc` (fetched via the authenticated tarball API).
Baseline suite: **597 passed, 1 skipped, 2 xfailed**.
After patch + these 4 test files: **600 passed, 1 skipped, 3 xfailed** (delta = +3 new passing, +1 new xfail).

Every test is authored RED against the branch as-is and GREEN against the reference fix, and asserts
BEHAVIOUR, not a specific implementation, so a fix of any shape that restores the behaviour turns it green.
Three of the four are clean RED→GREEN; M7-01 is decision-dependent and ships `xfail(strict=True)`.

Apply the fix with:

    git apply m6_review_fixes.diff

`git apply --check` passes on a pristine `4739b528bc` checkout. The diff touches only two source files
(`prospector/sensors/rebalance.py`, `prospector/runner/runner.py`) — no test files, no build artifacts.

---

## SNAP-01 (HIGH, confirmed bug) — snapshot-divergence fault never reaches the accumulator
`tests/test_snapshot_divergence_accumulator.py`

- **RED (branch):** `_materialize_snapshots` wires `write_snapshot(..., fault_sink=store.append)`. A
  divergence calls the sink and returns normally (the surrounding `except` only catches exceptions), so
  the fault is written to the STORE but never appended to the run's `faults` accumulator. The test drives
  the real seam over a SHADOW dispersion lead (so `page_worthy` is legitimately empty and the divergence
  is the sole page-worthy signal): accumulator = 0, `_compute_push` = False. Assertion fails.
- **GREEN (fix):** the sink is routed through `_emit_fault`, so the divergence lands in the accumulator
  (counted by the email scan-line and the next tick's comparand) AND drives `_compute_push` → True.
- **Why the suite missed it:** `test_snapshot_divergence.py::test_rewrite_with_different_state_and_sink_
  emits_one_fault` passes `fault_sink=faults.append` (a plain list) and asserts the sink is CALLED —
  production wires `store.append`, which does not reach the accumulator. The fixture unified a split path.
- **Fix shape (implementation-agnostic — any route into the accumulator passes):** in
  `_materialize_snapshots`, replace the raw `store.append` sink with one that calls `_emit_fault` (which
  also writes the store event, so the fossil record is unchanged). Re-opens the exact split-path bug the
  §10 taxonomy closed for sensors; this is the one remaining raw `store.append({'type':'fault'})`.

## R1 (HIGH, confirmed bug) — cash lines carry CUSIPs, so a cash sweep fires a spurious rebalance
`tests/test_runner_rebalance_cash_and_prior.py::test_pure_cash_sweep_does_not_accrete_a_rebalance`

- **RED (branch):** `_identified` (sensors/rebalance.py) excludes only rows with an EMPTY identifier. Real
  SSGA money-market/currency lines carry populated CUSIP-like identifiers (recorded TEKX file:
  `SSI US GOV MONEY MARKET CLASS` → `924QSGII3` @ 4.22%; `EURO CURRENCY` → `999EURZ94`), so they enter the
  diff. The test freezes a prior/today pair where ONLY the money-market line moves (+1%, past the 0.5%
  threshold; equities identical) and drives `_run_rebalance` over a shadow dispersion lead — a spurious
  `rebalance` accretes. Assertion fails.
- **GREEN (fix):** a cash/derivative exclusion keyed on the SSGA `-` TICKER sentinel (+ `MONEY MARKET`
  name, defense-in-depth) drops the cash line from the diff → no rebalance on a pure cash sweep.
- **Why the suite missed it:** every existing rebalance fixture builds cash-free equity baskets
  (identifiers 111/222/333) or a cash line with an EMPTY identifier — never a cash line with a CUSIP.
- **Fix shape — and the R2 caveat it respects:** the exclusion keys on the `-` ticker sentinel, NOT on the
  price-universe gate `holdings.priceable_members`. `priceable_members` ALSO drops foreign (non-USD)
  equities, whose genuine add/drop/reweight IS a rebalance signal (Siemens Energy, Schneider, etc.) —
  routing the diff through it would silence real foreign restructurings. The `-` sentinel excludes cash
  while keeping foreign constituents. An EXPLICIT `-` only: a missing/blank ticker column (synthetic
  frames omit it) is treated as "unknown", not cash, so the existing `test_rebalance_sensor.py` frames
  (no ticker column) are unaffected — all 9 still pass.

## R4 (MEDIUM, confirmed bug) — prior-parse fault has no stable §10 key, pages daily
`tests/test_runner_rebalance_cash_and_prior.py::test_unparseable_prior_fault_signature_is_stable_across_ticks`

- **RED (branch):** the current-feed rebalance fault passes a stable `key=f"{ticker}:{status}"`; its
  sibling 11 lines below — the prior-parse fault — passes NO `key=`, so `_fault_signature` falls back to
  the message, which embeds `prior_dates[-1]` (the newest frozen date < today). That date advances as
  pulls accumulate, so a persistently-unparseable prior yields a different signature every tick and pages
  daily. The test runs two ticks a day apart (prior date advances) and compares the real `_fault_signature`
  of the emitted faults — they differ (`XLK prior 2026-07-13: …` vs `XLK prior 2026-07-14: …`). Fails.
- **GREEN (fix):** the prior-parse `_emit_fault` gains a stable `key=f"{ticker}:prior:{status}"`; the
  message keeps the moving date for forensics but the suppression key is stable → identical signature
  across ticks → §10 suppresses the recurrence (pages once, then rides the heartbeat).
- **Why the suite missed it:** no existing test exercises a persisting unparseable prior across ticks.
- This is the §10 volatile-message nuisance-alarm (the `key=` mechanism from the email-suppression round)
  re-appearing on a sibling path the original fix did not touch.

## M7-01 (HIGH, confirmed bug — DECISION-DEPENDENT) — a missed weekly heartbeat is never caught up
`tests/test_runner_heartbeat_catchup.py`  ·  `@pytest.mark.xfail(strict=True)`

- **Finding:** `ops/run.sh` decides heartbeat day by wall clock (`date +%u -eq 7`, local Sunday) at the
  instant it executes. launchd coalesces a StartCalendarInterval fire missed while the Mac slept into a
  single catch-up run on wake — which runs `pros run` WITHOUT `--heartbeat`, so that week's heartbeat never
  sends. No "heartbeat overdue" state exists anywhere in `prospector/*.py` (grep-confirmed), so a skipped
  week is never made up. Because a MISSING weekly heartbeat is the project's defined "the runner is dead"
  signal, a benign sleep-across-Sunday produces a FALSE dead-man — the GPWS cry-wolf trap on the one
  channel whose job is unambiguous absence.
- **Why it is decision-dependent (xfail, not RED→GREEN):** the fix requires a design choice the QA seat
  should not make unilaterally — WHERE the catch-up decision lives (move it into the runner, or keep it in
  `run.sh` reading a runner-exposed "due?" signal) and WHAT records "last heartbeat sent" (a `heartbeat.sent`
  event, a runlog column, or reusing `recent_runs`). The test encodes only the implementation-agnostic
  behavioural contract and is `xfail(strict=True)`: it does NOT fail today's suite, and it flips to a loud
  XPASS the moment a catch-up mechanism lands — the signal to remove the marker (mirrors the N9
  deferred-gate pattern).
- **Behavioural contract asserted:** a non-heartbeat-day tick, when the last heartbeat is older than the
  weekly cadence (a Sunday was missed), must still send a catch-up heartbeat; and a tick with a heartbeat
  sent within the cadence must NOT re-send (no double-paging). Expressed against a proposed
  `heartbeat_is_due(registry, now, cfg)` + `record_heartbeat_sent(store, ts)` surface — the NAMES are
  illustrative; realign to whatever interface the fix adopts, then delete the xfail marker.
- **Companion judgment findings (no test, reported in `m6_deep_review_findings.md`):** M7-02 (backup
  health never reaches the weekly email) and M7-03 (the in-email "Heartbeat: OK/BROKEN" line is
  structurally always OK) compound with M7-01 into one operator blind spot; worth deciding together.

---

### Verification performed
- RED against pristine `4739b528bc`: R1/R4/SNAP-01 fail (3 failed), M7-01 xfailed. Baseline 597 passed.
- GREEN against branch + `m6_review_fixes.diff`: all 3 pass, M7-01 xfailed. Full suite 600 passed, 1
  skipped, 3 xfailed.
- `git apply --check m6_review_fixes.diff` clean on a pristine checkout; diff is 2 source files, no test
  files, no build artifacts.
- The R1 fix does not regress the 9 existing `test_rebalance_sensor.py` tests (the empty-identifier and
  no-ticker-column cases both still behave).
