# Prospector — deep cold-read QA of the last 4 days (branch `m6-discourse-capture`)

**Reviewed:** branch `m6-discourse-capture` (unmerged) vs `main`, the ~90 commits since 2026-07-09.
**Seat:** Claude Science (QA) → for the Claude Code (implementation) seat.
**Method:** four parallel cold-read tracks over the new subsystems, then every HIGH finding re-verified
by hand against the real code / the recorded-real TEKX fixture. Nothing below is asserted from a green test.
**Branch health:** full suite **597 passed, 1 skipped, 2 xfailed** — green. *A green suite is not evidence*;
this project's recurring failure mode (now 3× before this round, all on the alarm layer) is code that passes
its own fixtures but breaks on real data, so the hunt targeted fixture-only assumptions specifically.

## Scope covered
M7 autonomy core (launchd scheduled runner + dead-man heartbeat) · prod-worktree deploy · store dual-HDD
backup §7 + the exFAT mtime-window fix · machine-local config overlay · §10 fault taxonomy · rebalance
runner-wiring §4d. (M6 discourse-capture itself was reviewed separately — see `m6_capture_review.md`.)

---

## Findings at a glance

| # | Sev | Class | Subsystem | One-line |
|---|-----|-------|-----------|----------|
| **M7-01** | HIGH | BUG | M7 dead-man | A Sunday run coalesced to a Monday catch-up (Mac slept) runs without `--heartbeat` → the week's dead-man signal is silently dropped while the system is alive |
| **SNAP-01** | HIGH | BUG | §10 / snapshots | Snapshot-divergence fault writes to the store but bypasses the faults accumulator → a data-integrity invariant break is never counted and never pages |
| **BK-1** | HIGH | BUG | backup §7 | A blessed drive failing mid-copy (ENOSPC / unplugged) escapes uncaught, skips the healthy drive, records no failure → "best-effort-but-loud" is violated exactly when a drive degrades |
| **R1** | HIGH | BUG | rebalance §4d | Real SPDR cash/money-market lines carry CUSIPs, so the "identified securities only" guard excludes nothing → benign daily cash-sweep wiggle fires spurious "restructuring" corroboration onto live leads |
| **M7-02** | HIGH | JUDGMENT | M7 / backup | Backup runs after the heartbeat in a separate process and writes no fault event → the weekly email (the operator's only health channel) reports "Health: OK" while backups fail for weeks |
| **M7-03** | MED | BUG | M7 email | The in-email "Heartbeat: OK/BROKEN" line is structurally always OK — its BROKEN branch is unreachable in any sent email |
| **R3** | MED | BUG | rebalance §4d | Two cash/derivative lines sharing the `-` sentinel collapse to one diff key; the lighter one silently vanishes |
| **R4** | MED | BUG | rebalance §4d | The prior-parse fault embeds a moving date with no stable `key=` → the §10 volatile-message nuisance-alarm its own sibling path already fixes |
| **BK-2** | MED | BUG | backup §7 | mtime-window aliasing: a same-size content change within 2s of the prior backup is silently skipped, leaving a stale copy on the HDD |
| **M7-04** | MED | JUDGMENT | deploy | `deploy.sh` can swap code/deps under an in-flight scheduled tick — no lock coordinates the two |
| **M7-05** | MED | JUDGMENT | M7 | Heartbeat day keys on LOCAL weekday while the cadence anchor is UTC; `schedule.weekly_day` is dormant (read nowhere) so the "keep in sync" comment guards nothing |
| **R2** | MED | JUDGMENT | rebalance §4d | The *naive* fix for R1 (route the diff through `priceable_members`) would wrongly drop foreign equities, whose genuine add/drop IS signal — fix needs a cash-sentinel test, not the price-universe gate |
| **BK-3** | LOW | JUDGMENT | backup §7 | Fire-and-forget copy: no post-copy read-back/checksum (the store's own `write_atomic` does this; backup doesn't) — partly a deliberately deferred item |
| **M7-06** | LOW | JUDGMENT | M7 | No single-instance lock / no `busy_timeout` PRAGMA; concurrency safety rests entirely on launchd serialization + atomic appends (a documented `kickstart -k` escape hatch can bypass it) |
| **GI-01** | LOW | JUDGMENT | config | Couldn't verify `prospector.local.yaml`/`.env` are gitignored — the source export carried no `.gitignore` (unverifiable, not a reproduced defect) |

**4 HIGH confirmed bugs + 1 HIGH design-judgment. Three of the five HIGH items are on the alarm/fault
layer** — the same class this project keeps getting bitten by. That is the signal.

---

## HIGH findings (detail)

### M7-01 — coalesced-Sunday catch-up silently drops the weekly heartbeat (a false dead-man)  · CONFIRMED BUG
**`ops/run.sh:30` + `ops/com.prospector.run.plist` (StartCalendarInterval)**

The heartbeat is armed only when `run.sh` sees `date +%u -eq 7` (local Sunday) **at the instant it executes**.
launchd, by design, coalesces a `StartCalendarInterval` fire that was missed while the Mac slept into a
single catch-up run **on wake** — and that catch-up runs at wake time, not the original scheduled time. So a
Mini asleep across the Sunday fire (a sleeping Mac is the exact premise for choosing launchd over cron) wakes
Monday and runs `pros run` with `date +%u == 1` → **without `--heartbeat`**. That week's heartbeat never
sends. There is no last-heartbeat / "overdue" state anywhere in `prospector/*.py` (grep-confirmed), so a
skipped week is never made up.

Because a *missing* weekly heartbeat is the project's defined "the runner is dead" signal, a benign
sleep-across-Sunday produces a **false dead-man**: the operator either investigates a healthy system (the
GPWS §2.4 cry-wolf trap that trains them to ignore it) or, if they habitually sleep the Mini Sunday nights,
the heartbeat *never* fires and a genuinely dead week is indistinguishable from the benign case.

*My verification:* `date +%u` returns the local weekday at call time (confirmed on this box); `run.sh:30` is
the only heartbeat-day decision and reads the clock at execution; grep confirms no `last_heartbeat` /
`heartbeat_due` / catch-up state exists. launchd coalesce-on-wake is documented Apple behavior. *Tests miss
it* because no test references `run.sh`, launchd, or `date +%u`; `test_email_render` only checks that
`render_heartbeat` produces an email when *handed* a ctx — never whether the scheduler decides to pass
`--heartbeat` on the right day, which is the actual arming logic.

### SNAP-01 — snapshot-divergence fault bypasses the §10 accumulator (surfaced, never counted, never pages)  · CONFIRMED BUG
**`prospector/fold/snapshots.py:130-133` (the `fault_sink` call), wired at `runner.py:1168` (`fault_sink=store.append`)**

`write_snapshot`'s divergence guard — which fires on "a backdated event or a nondeterministic fold (invariant
break)", a genuine data-integrity break — emits its fault by calling `fault_sink({...,"type":"fault"})`
directly. The runner wires `fault_sink=store.append`, so the event lands in the store but is **never**
appended to the run's `faults` accumulator. Everything downstream reads the accumulator, so all of it goes
blind: the email scan-line count (`len(op)` from `_partition_faults(ctx["faults"])`) shows **0**; `_compute_push`
reads only `faults`, so it **never pages**; and it never enters `runlog.faults` for the next tick's
comparison. `runner.py:142` carries a comment *explicitly forbidding this* — "never a raw
`store.append({"type":"fault"})` — route through the ONE `_emit_fault` accumulator." The snapshot path
violates the runner's own stated rule.

This is the *exact* "0 faults printed beside faults that fired" symptom the §10 Follow-up-2 fix closed for the
sensor layer — re-opened on the snapshot layer. The author's docstring (`snapshots.py:117-120`) believed
`store.append` "reaches the fault-email surface"; that was true pre-§10, but post-§10 the alarm surface
(count + page) is the accumulator, not the store.

*My verification (real code, no fixtures):* built a `StoreLayout`+`Registry`, wrote a snapshot for
`(lead, ts)`, then re-wrote the SAME `(lead, ts)` with divergent state and `fault_sink` capturing events.
Result: **faults accumulator len = 0, fault events to store = 1, `_compute_push({}, [], []) = False`**.
Counted 0 / paged False / body-shows 1. *Tests miss it* because `test_snapshot_divergence.py` drives a real
divergence but passes `fault_sink=faults.append` — a plain list standing in for the accumulator — so the test
asserts the fault reaches `faults`; production wires `store.append`, which does not. Textbook
fixture-hardcodes-the-happy-path.

### BK-1 — a blessed drive failing mid-copy skips the healthy drive and records no failure  · CONFIRMED BUG
**`prospector/store/backup.py:140-155` (loop body, no per-target try/except); `cli/main.py:157` (catches only `BackupError`)**

The blessing check (`backup.py:141`) is the *only* guarded failure mode. Once a target is blessed,
`_mirror_tree` / `backup_sqlite` run with **no exception handling**. If a blessed drive fails partway through
the copy — external HDD fills (ENOSPC), gets unplugged, or the `.backup` fails — the `OSError` propagates
straight out of `backup_store()`. Targets are processed in a serial for-loop, so **any target after the
failing one is never reached**: the healthy second drive gets nothing. No `report.failures` entry is
appended, the failing drive is left with a torn partial mirror, and the CLI's `except` (main.py:157) catches
only `BackupError` — so the operator gets a raw Python traceback instead of the designed
`FAULT <target>: … the record is NOT fully backed up` line. The exit is non-zero (loud) but it's the *wrong*
loud: it doesn't name the drive, doesn't say the record is unbacked, and hides that the good drive was
skipped. The durability guarantee is a lie for that cycle — exactly when a drive is degrading.

*My verification:* read `backup_store` — the loop body (140-155) has no try/except after the blessing check;
the CLI except catches only `BackupError`. The sub-agent additionally reproduced it by monkeypatching
`shutil.copy2` to raise `OSError(28)` under the first target: `backup_store` raised, the second target's
`events/` was never created, `report.failures` was never populated. *Tests miss it* because `test_backup.py`
exercises fail-loud only for the **unblessed/unmounted** case (a target that fails the blessing check *before*
any copy) — never a blessed target that raises *during* the copy. Synthetic temp-dir targets never fill up or
vanish mid-copy, so the "both HDDs present, one degrades" scenario the design promises to survive is the one
the fixtures can't produce.

### R1 — the rebalance diff includes real cash/money-market lines (the exclusion guard excludes nothing)  · CONFIRMED BUG
**`prospector/sensors/rebalance.py:72-87` (`_identified`); driven from `runner.py:907,923` (raw `load_frozen`, never `priceable_members`)**

`_identified` documents and relies on "Cash/derivative rows carry an empty identifier … excluded here so
their daily wiggle never reads as a rebalance," skipping only rows where `if not ident`. **On the
recorded-real TEKX file, every one of the 35 rows carries a populated CUSIP-like identifier** — the
`SSI US GOV MONEY MARKET CLASS` line has `924QSGII3` (weight **4.22%**) and the `EURO CURRENCY` FX line has
`999EURZ94`. Both enter the diff keyspace. Since materiality treats any add/drop as material and applies the
0.5% threshold to weight deltas, two benign live-data behaviors fire: (A) a money-market sweep balance
drifting >0.5% day-over-day emits a material weight-delta rebalance; (B) a tiny FX/cash line flickering out of
the file emits a material *drop* (add/drop ignores the threshold entirely).

Rebalance never pages — but it **accretes "this basket is restructuring" corroboration onto every live lead's
timeline**, including shadow dispersion leads in their 90-day burn-in. That corroboration is exactly the
evidence an operator weighs when promoting a lead to paging. A cash-wiggle alarm that fires on benign input is
the cry-wolf pattern one layer down: it pollutes the corroboration record the whole design rests on.

*My verification (real TEKX fixture):* `parse_spdr_holdings(tekx, "TEKX")` → 35 rows, **0 with an empty
identifier**, `_identified` keeps **35/35**, and both cash identifiers (`924QSGII3`, `999EURZ94`) survive into
the keyspace. A money-market +0.6% / NVDA −0.6% shift → `material: True` with
`weight_deltas=[('NVIDIA CORP', −0.006), ('SSI US GOV MONEY MARKET CLASS', 0.006)]`. Dropping the
0.0000015-weight euro-dust line → `material: True` drop. *Tests miss it* because every diff-exercising test in
`test_runner_rebalance.py` builds its bodies from pure-equity rows with clean identifiers `111/222/333` and no
cash line in the *diffed* basket; the synthetic XLK fixture's cash line is identical in prior and current, so
no cash delta is ever produced. The suite proves the diff correct on data whose shape is the opposite of the
real file's.

**Fix caution (R2, MEDIUM/JUDGMENT):** the obvious fix — route the diff through the existing
`priceable_members()` — would *also* drop foreign equities (Siemens Energy AG, EUR, 6.17% of TEKX; Schneider
Electric, EUR) and the un-priceable-ticker ExxonMobil placeholder. Those are *real constituents* whose genuine
add/drop/reweight is signal, not noise. `priceable_members` is the §9e **price-universe** gate ("can I fetch a
US price"); the rebalance diff needs a **cash/derivative** exclusion ("is this a real security position") —
e.g. a money-market/currency name test or the `-` ticker sentinel. Don't reach for the wrong existing helper.

### M7-02 — backup health is invisible to the weekly heartbeat  · HIGH / DESIGN JUDGMENT
**`ops/run.sh:33-37` (`pros backup` after the heartbeat run) + `backup.py` (no fault event) + the email body (faults from store folds only)**

`run.sh` runs `pros run [--heartbeat]` first (which sends the weekly email), *then* `pros backup` as a
separate process. `backup_store` writes **no fault event** into the fossil store — a failure surfaces only as
a non-zero exit in the launchd `StandardErrorPath` log. So the heartbeat's `Health:` line and recent-faults
section (computed purely from store folds) can never reflect a backup failure. The operator whose *only*
designed health channel is the weekly email ("read the email, not the logs" is the whole point of the weak,
self-owned dead-man) sees "Health: OK" while the irreplaceable fossil record goes un-backed-up. Ordering
compounds it: backup runs *after* the heartbeat, so even a same-tick backup fault couldn't reach that tick's
email. This is design-judgment rather than a code bug — but it's the highest-consequence *silent* degradation
in the subsystem: a failed backup is exactly when you need to know, and the primary channel is blind to it.
(Related to M7-03 below and BK-1 above — the three compound: a drive degrades → BK-1 hides which drive → M7-02
keeps it out of the email → M7-03's liveness line still says OK.)

---

## What was checked and found GOOD (so these don't read as unreviewed)

Each was a plausible failure site verified against real code and found correct:

**M7 / ops**
- launchd-not-cron catch-up works for **runs**: the plist uses `StartCalendarInterval` only, so a missed run
  IS coalesced on wake. Only the heartbeat-*day* selection (M7-01) breaks on the same mechanism.
- Env chain under launchd's minimal environment is sound (REPO_ROOT via `BASH_SOURCE`+`cd`; PATH prepends uv
  dirs; `.env` via `setdefault` so an exported value wins).
- `run.sh` does not skip backup on a soft-faulting-but-completing tick (`set -e` + `pros run` exit 0 on soft
  faults); a hard crash correctly stops before backup, after the tick's own fault email fired.
- SMTP send failure is caught as a soft `notify` fault so snapshots + run-log still write; `--heartbeat` with
  no `smtp_host` prints a note rather than failing the tick.
- Read-only dashboard concurrency: writer sets WAL, read surface opens `mode=ro` (not `immutable=1`).
- `deploy.sh` enforces deploy-from-tag by mechanism (rejects non-tag refs up front; aborts on dirty tracked
  config; the gitignored overlay survives a tag checkout).
- The store is external to every checkout (`~/prospector/store`, sibling of dev/prod worktrees) — no
  checkout/deploy can touch the fossil record.

**Backup §7**
- `registry.sqlite` goes through the `.backup` API (WAL-safe), never a raw copy; no `-wal`/`-shm` sidecars
  copied; verified `integrity_check = ok`.
- Blessing-marker fail-loud is correct for the **unmounted/unblessed** case (recorded in `failures`, dir
  never created — guards the "/Volumes phantom onto the internal disk" footgun). *Only the mid-copy case fails
  — BK-1.*
- No-targets-configured raises `BackupError` → non-zero exit; repo ships `backup.targets: []` so a dev box
  faults loudly rather than silently no-op'ing.
- `verify_restore` rebuilds a throwaway store from fossils alone via reindex (still succeeds with
  `registry.sqlite` deleted).

**Config overlay** — all four hunt targets came back clean:
- **Hash is computed AFTER the deep-merge** (`config.py:53-54`): an overlay that changes *behavior*
  (e.g. `xcorr.z_in 2.5→3.5`) moves the hash → `config.changed` fossil fires. The append-only record does not
  lie about live config. This was the make-or-break concern and it holds.
- Deep-merge recurses on nested dicts, replaces scalars/lists wholesale, preserves siblings, mutates neither
  input (no silent sibling-drop).
- Overlay resolved as a sibling of the passed path (not cwd-relative); a non-mapping overlay raises a clear
  `ValueError`.
- `config.py` never touches `os.environ` — secrets stay in `.env` and never enter the fossilized hash.

**§10 taxonomy** — routing verified end-to-end:
- Operational faults page; a review-advisory on a non-live lead is counted/displayed but suppressed from
  paging; an advisory on a live lead pages; an unknown/legacy category defaults to **operational** (fail-safe).
- All *sensor* advisories route through the `_advisory_reporter` (mandate.py, soi.py) — never a raw
  `store.append` — so the split-path bug is closed on the sensor layer. **The one remaining raw-`store.append`
  fault write is the snapshot guard (SNAP-01).**
- The §10 suppression fix (`_fault_signature` keyed on `(subsystem, key or message)`) round-trips through the
  fossil: recovered prior faults carry `key='AAPL:403'`, the signature is stable when only the URL date moves,
  a changed status (403→500) still pages. My volatile-message fix from last round stays closed on the real path.

**Rebalance §4d**
- The diff keys on the **CUSIP/identifier, not ticker** — the ENR foreign/US-collision lesson is correctly
  defended at the diff grain (Siemens Energy vs Energizer, both `ENR`, produce zero spurious deltas).
- H1 ÷100 lineage is safe: `parse_spdr_holdings` enforces the `[0.5,1.5]` weight-sum band on every parse, and
  both diff inputs go through it — a fraction-valued file raises rather than silently shrinking 100×.
- Seed/fault boundary matches the ratified decision (first-sight seeds silently; a broken current feed faults
  operationally and continues). Idempotency keys on `(series_id, as_of)` from the record, not the payload.
- Shadow-inclusive routing is a deliberate, ratified divergence (rebalance accretes, never pages, so it
  *should* corroborate burn-in shadow leads) — matching intent, not a smell.

---

## Suggested triage order

1. **SNAP-01** and **R4** are one-line-ish alarm-routing fixes with an outsized correctness payoff (both are
   "the alarm silently doesn't fire / cries wolf"), and both sit in code paths you've already hardened once —
   they're the cleanest wins.
2. **M7-01** (heartbeat catch-up) is the most consequential *design* fix: the dead-man needs a "heartbeat
   overdue" notion (track last-heartbeat-sent, arm on the first run where a week has elapsed) rather than a
   wall-clock day gate. This is the difference between a dead-man that works and one that cries wolf every
   time the Mac sleeps on a Sunday.
3. **BK-1** (per-target try/except in the backup loop + widen the CLI `except`) restores the durability
   contract; **M7-02** (surface backup health into the heartbeat) closes the observability gap that makes
   BK-1 dangerous. Worth doing together.
4. **R1** needs the cash/derivative exclusion done *right* (per R2) — a sentinel/name test, not the
   price-universe gate.

## RED-first tests + reference patches

Every HIGH here (and R3/R4/BK-2/M7-03) is reproducible, which means each can get the same treatment as the
§10 and N-series work: a RED-first regression test that fails against the branch and goes green after the fix,
plus a `git apply`-able reference diff, verified against a clean checkout. Say which ones you want and I'll
draft them — I'd suggest starting with **SNAP-01, R1, R4, M7-01** (the four with the highest
alarm-integrity payoff). I won't touch implementation until you've got the tests you want in hand, per the
usual split.
