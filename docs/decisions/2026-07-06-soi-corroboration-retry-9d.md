# §9d — the deferred SOI-corroboration retry loop (M5 build-order step 3, part 1)

*Decision record, 2026-07-06. Implements spec `docs/prospector-m5-runner-spec-2026-07-05.md` §9b/§9d
(SUBTLE BIT #3), on top of the runner skeleton, step-2 SOI-fetch (`resolve_soi_target`), and the M4 SOI
resolver. This is where step 2's fetch machinery finally gets used. §9c (mandate frozen-prior) and §9e
(shadow clock) — the other two of step 3 — remain SLOTs, to land next.*

## What was built

The runner now runs a deferred SOI-corroboration pass each tick (`runner._run_soi_corroboration`, wired
at the §9d SLOT in `_run_sensors`):

1. **Enumerate the work-list from the FOLD (§9f), never a side table** — `pending_soi_resolution`
   (`sensors/launch_corroboration.py`, a pure function) folds every `launch` event across all leads,
   keeps the latest per series by `(ts, event_id)`, and returns those whose latest disposition is still
   `sectors_unresolved` and whose detection is within the retry horizon. A later `match` (on a lead) or
   `dormant_no_match`/`no_dominant_sector` (on `_system`) supersedes, so a resolved launch drops off —
   the same append-only-supersession the record already uses, the same single-source enumeration as
   active leads.
2. **Resolve + drive** — for each pending launch: look up its registry entry (cik + fund-name anchor),
   call `resolve_soi_target(cik, client)` (step 2), and drive `sensors/soi.scan` with the fetched SOI
   bytes. `soi.scan` → `route_corroboration` reaches back preserving the original `detected_at` as **T2**,
   so the cross-stream lag measures to detection, not to when the SOI arrived.
3. **`_active_lead_sectors`** assembles the overlap map live: resolve the sector-ETF universe tickers to
   series_ids via the registry, bridge to GICS sectors (`sector_map`), and `lead_sectors()` over the
   active (non-shadow) leads.

## The gate: the three-property fires-not-called test

§9d is the subtlest of the four runner "subtle bits" — its failure mode is wiring that finds ∅ (holdings
/ SOI post days later) and **silently never fires**. So the test proves the pass actually fires, three
ways (`tests/test_runner_soi_corroboration.py`), plus the §9f enumeration:

1. **It fires when sectors land** — a launch recorded `sectors_unresolved`, its real TEKX NPORT-EX
   arrives, the pass accretes a `match` onto the overlapping XLK×XLU lead (not merely "it was called").
2. **It reaches back with T2 preserved** — the `match` payload's `detected_at` is the original detection,
   and `cross_stream_lag` computes **+593 days** (T2 2024-09-09 − T1 2023-01-25), not a lag to the SOI's
   arrival.
3. **It stays dormant gracefully on a not-yet** — when `resolve_soi_target` returns None (SOI unindexed /
   ambiguous exhibit), the launch stays `sectors_unresolved`, is still on the work-list next cycle, and
   the run continues with **no fault** (a not-yet is not an error).

Plus: `dormant_no_match` when there's no live lead to overlap; a per-launch fetch failure is a **soft
fault** (recorded, skipped, the pass continues, §9g); and the §9f enumeration (a resolved `match`
supersedes, so the launch drops off).

## Decisions

- **Retry horizon `corroboration.retry_horizon_days: 365` (DEFAULT, not CONTRACT).** A safety valve
  against re-fetching ancient launches, deliberately generous: a fund's first sector-bearing NPORT-EX is
  filed 60 days after a fiscal quarter-end, so a fund listing just after one can wait the better part of
  a year for its first — a year's headroom catches that reliably. (Chosen after the test surfaced that a
  180-day horizon would age out the real TEKX case, whose usable SOI is ~a year past detection.) Launches
  past the horizon stay dormant-terminal and are surfaced by the coverage report (§10, deferred), never
  re-fetched forever.
- **No weekly cadence gate.** The runner is cadence-agnostic (cron drives it; `schedule.weekly_day` is
  M7). §9d attempts each pending launch every tick, bounded by the horizon. Throttling the SOI-heavy
  fetch to weekly (§9b's "SOIs post ~quarterly, so a daily re-fetch is waste") is an M7 scheduling
  concern, not a correctness one — noted in the code.
- **Enumeration across all leads, not just `_system`.** The original `sectors_unresolved` is on `_system`
  but its resolving `match` lands on the lead; to detect resolution, the fold reads `launch` events
  across every lead. Read via `registry.events_for_lead(lead, "launch")` (the row carries `event_id` for
  the `(ts, event_id)` total order; `read_lead`'s Envelope drops it).

## Coverage bounds (honest, named — the mechanism is what lands here)

§9d's *live* yield is bounded by three upstream pieces that are their own SLOTs — exactly the SPDR-only
holdings-coverage pattern, flagged not hidden:
- **Input**: `sectors_unresolved` launches are produced by the **holdings corroboration pass**
  (`corroborate`, a separate §9a/§4c SLOT not yet wired), so live there are none yet.
- **Overlap**: matches need live **xcorr/dispersion leads** (their own SLOTs), so `_active_lead_sectors`
  is currently empty → `dormant_no_match`.
- **Anchor**: the fund-block anchor is the registry entry's `name`, which must be a stable unique STEM
  (§9b — TEKX was "SPDR Galaxy…" then "State Street Galaxy…", so key on `Transformative Tech
  Accelerators`). A launch resolved to the trust name won't isolate its block → `soi.scan` faults
  (extraction-unreliable) → stays `sectors_unresolved`. The proper fund-name source (etfdb skim) is
  deferred.

None of these block the runner; the mechanism is wired and tested, ready to yield as the upstream lands.
No CONTRACT touched (retry_horizon is a DEFAULT; no schema change; `FundEntry` untouched).

## Tests

413 pass (was 407; +6). All offline: the EdgarClient fetch is injected over in-memory submissions/index
fixtures + the real frozen TEKX SOI; the socket guard fails any real connection. A run_tick assertion
pins that the real driver reaches the §9d SLOT.

## Still deferred (step 3 remainder + named)

- §9c — the mandate frozen-prior invariant (the diff's prior is the last frozen prospectus blob, never
  the registry `prospectus_accession`); §9e — the dispersion shadow clock (surface readiness, never
  auto-promote).
- The holdings corroboration pass that *creates* `sectors_unresolved` (a §9a/§4c SLOT); live xcorr/
  dispersion leads (§4a/§4b SLOTs); the etfdb fund-name source for the anchor; the weekly SOI-fetch gate
  (M7 scheduling).
