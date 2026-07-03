# Dispersion ships shadow-first; PIT backtest + NPORT deferred

**Status:** design-thread guidance, ratified 2026-07-03 (spec §4b, §3b, §12). Records three build-time
decisions made while implementing the dispersion sensor (`prospector/sensors/dispersion.py`) and its
holdings-ingest keystone (`prospector/ingest/holdings.py`): the live-burn-in-first sequencing, the
generous-payload persistence default, and a shared-module change to the Schmitt helper. No CONTRACT
was created here except the one rev8 already ratified (the generous payload, see
`docs/decisions/2026-07-03-dispersion-payload-generous.md`); this is scope + defaults + a flagged
refactor.

## 1. Live burn-in first; the §3b PIT backtest + NPORT-P are deferred

The dispersion sensor ships on the **issuer daily CSV** path (SPDR holdings → 90%-weight membership →
constituent-correlation → Q departure-z), **shadow-wired** for its first 90 days (§4b CONTRACT). The
historical **point-in-time backtest** (§3b / test 6) — reconstructing basket membership from
quarterly EDGAR NPORT-P filings back to ~2019 and pricing delisted constituents from the free EOD
source — is **deferred**, for reasons the spec already sanctions:

- **The spec permits it.** §3b: "if [delisted-constituent price] coverage is poor, fall back to live
  burn-in only, and say so." And shadow mode applies at go-live *regardless* of the backtest — "the
  backtest earns calibration, not paging." So the PIT backtest is not on the critical path to
  shipping a shadow dispersion sensor.
- **It is a heavier, separable slice.** It needs an NPORT-P XML parser, PIT membership reconstruction,
  and a *measured* delisted-constituent price-coverage fraction from the free source — each its own
  work, and the coverage may be poor. `parse_nport_holdings` lands here as a documented thin
  signature (`NotImplementedError`) so the seam exists without a half-built parser.
- **It is worse here than for xcorr** (Appendix B's caveat): the acquired winners — precisely the
  names bought *because* their thesis turned out real — vanish from the survivor set, biasing any
  historical run against the very signals dispersion exists to find. Live-forward watching is clean;
  the backtest is not, and must not be trusted until that data question is solved.

**Consequence honored in code:** the pure pipeline (`dispersion_q_series` and friends) is written
**membership-agnostic** — it takes a returns panel and a fixed membership — so the deferred PIT
backtest can later drive it over reconstructed membership with **no change to the sensor**. This is
the launch sensor's ratified "capture-first, interpret-later" shape
(`2026-07-03-launch-sensor-capture-first.md`) one more time: the continuously-running, un-backfillable
half ships now; the historical interpretation waits on its data.

## 2. `correlation_detail: full` is the default during shadow burn-in

The generous payload (§4b CONTRACT) must let the deferred v2 proto-cluster layer thaw backward, and
**you cannot backfill a payload you did not capture.** The knob `dispersion.correlation_detail`
(`full` | `topk` | `summary`) governs how much constituent correlation structure each `dispersion.tick`
persists. **DEFAULT `full`** (the whole pairwise matrix), because:

- **No-backfill dominates.** During the shadow burn-in the substrate is being banked for a layer that
  does not exist yet; capturing *less* now is an irreversible loss, capturing *more* is cheap.
- **Volume is trivial.** The tick cadence is weekly, n is bounded by the 90%-weight cut (~dozens of
  names), across ~11 baskets — kilobytes per week. There is no volume argument for thrift yet.

`topk` (the strongest within/cross pairs + summaries) and `summary` (within/between means only) exist
for after promotion, if volume ever matters. The within/between summaries are persisted at *every*
detail level — they are the scalar backbone the fold and any future reader can always rely on.

## 3. Schmitt state reconstruction generalized (a flagged shared-module change)

`schmitt.state_from_last_event_type` (a §4 shared surface, used by both departure sensors)
reconstructed the trigger's ACTIVE state **only** from a `.departure` last event. **Dispersion has no
`.departure` event** (spec §5: only `dispersion.tick` / `dispersion.reverted`), so under the old rule
an actively-*ticking* dispersion lead would reconstruct as QUIET and **re-spawn every run.** The
helper now reads: **QUIET on no-prior-event or a `.reverted` exit; ACTIVE otherwise** — keying off the
single `.reverted` exit convention (the same one the fold uses to fold any `*.reverted` to
`status=reverted`). This is correct for both sensors and safe (the only caller was
`tests/test_schmitt.py`, updated). Flagged rather than smuggled because it touches a shared trigger
module; dispersion is its first real production caller.

## What shipped (2026-07-03)

- `prospector/ingest/holdings.py` — SPDR daily-CSV parse, 90%-weight membership, freeze-before-parse
  under `ingest/holdings/{series_id}/{date}/`; `parse_nport_holdings` a deferred thin signature.
- `prospector/sensors/dispersion.py` — the pure pipeline (constituent returns → correlation →
  spectral bipartition → Q → Q departure-z reusing `xcorr.departure_z`), the per-basket driver, and
  the **generous `dispersion.tick` payload** builder; shadow-wired lead spawn.
- `prospector/sensors/schmitt.py` — the generalized state reconstruction (item 3).
- `config/prospector.yaml` — the dispersion knobs (`window_days`, `baseline_days`,
  `min_constituents`, `method`, `tick_cadence_days`, `correlation_detail`, `correlation_top_k`).
- Tests: `test_holdings.py`, `test_dispersion_math.py`, `test_dispersion_sensor.py`,
  updated `test_schmitt.py`.

**Not built (deferred, named):** the §3b dispersion PIT backtest + NPORT-P parser + delisted-price
coverage measurement (item 1); the launch corroboration hook (unblocked now that holdings ingest
exists — the next slice per `2026-07-03-launch-sensor-capture-first.md`); the rebalance sensor; the
live §9 cadence runner (M5+) that will call `dispersion.scan` daily and wire `emit` to the store.
