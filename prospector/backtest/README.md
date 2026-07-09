# `prospector/backtest/` — offline calibration + the milestone-3 acceptance gate

This package replays the `xcorr` sensor over **frozen** price history to calibrate thresholds
and to produce the milestone-3 acceptance artifact (spec §10 test 5, a CONTRACT gate the human
reviews). Everything here is offline/historical and **walled off from the live fossil record**.
It is **built** (M3 landed); it is invoked only by `pros backtest --from … --to … [--sweep]`,
never by the M5 runner.

## The CONTRACT that shapes everything here

Backtests write **ONLY under `backtest/`** — each run gets its own store root
(`backtest/run_{stamp}/`) with its own `registry.sqlite`, so synthetic history can never touch
the live `events/` tree (spec §7). The guard is **structural** (`StoreLayout(kind="backtest")`),
not a conditional. The scorer's `keyword_match` + the curated launch table
(`tests/fixtures/backtest/historical_launches.yaml`) are backtest-only and **never enter the
live path**. Every threshold this package reports is **human-ratified, never auto-tuned** — the
report lays out evidence; it does not decide pass/fail (a "no" is the system working, §12).

## Modules

- **`runner.py`** — Replays the sensor over frozen prices. `compute_z_and_stress()` runs the pure
  `xcorr` pipeline once (panel → per-pair departure-z + absolute market-stress level); `replay()`
  drives the Schmitt trigger per pair honoring the crisis gate (a stressed day freezes the trigger
  and records a `market_stress=true` departure onto `_system`); `sweep()` re-triggers across the
  `(z_in, z_out)` grid over that fixed z-panel. `run()` persists firings into a backtest-only store.
  Also carries the **concept validators** the gate is held to — `beta_strip_health()` (the §4a
  before-tuning diagnosis: does the β-strip actually collapse residual correlation in a crash?),
  `stress_concept_validation()` (gate fires on acute crises, stays open in sustained grinds, quiet
  on calm days — **plus the aging monitor**, see below), and `crash_falsification()` (the amended
  March-2020 test: a crash-window spawn is "free" only if it **reverts** within the bound).
- **`report.py`** — Assembles the §10 acceptance artifact (`build_report`) and renders it
  deterministically to JSON + Markdown (`render_markdown`, no generated prose). Four sections:
  **(a) recall** (the XLK×XLU timeline), **(b) precision** (full firing list, each corroboration-
  scored, + the threshold sweep), **(c) falsification** (the three-part rev5 §10.5c verdict), and a
  **cross-stream lag** bonus. This is also where the **stress-gate aging monitor** surfaces: it
  reports the recent **calm-regime p95** (crisis days excluded) and its **headroom** to the frozen
  gate — a **tripwire for human recalibration**, never a self-tuning rule (a rolling percentile
  would reintroduce the rejected baseline-relative form).
- **`corroboration.py`** — The §10 test 5b scorer. A firing is `structural` iff a curated launch
  whose concentration industries keyword-match **both** sides of the pair lands within W months of
  first firing. `keyword_match` uses a word-boundary guard on short tokens (`_MIN_FREE_SUBSTRING`)
  so `'ai'` doesn't forge bridges through `'retail'`. Carries a load-bearing **honesty caveat**: it
  bakes in "packaged = real", a conservative bias (a missing launch can only make precision look
  worse), not a truth.
- **`beta_diagnostic.py`** — The crash-flags diagnostic (the multi-factor-β guard). A **SCOPED,
  READ-ONLY** analysis that is **explicitly NOT part of the sensor** and is imported by nothing in
  the sensor/runner paths. On just the flagged pairs it compares residual correlation under the
  production 252d β vs a faster β (`scoped_beta_slice`: stale-β artifact box A vs idiosyncratic
  box B/C) and reads the β-window-roll clock vs the rates clock (`two_clock_read`). The M3 outcome
  ruled out box A, so **no estimator swap is warranted — do not wire this in** (a sensor-wide β
  change would move the +593 recall signal and force a full M3 re-validation).

## Important to know

- The sensor keeps its **production 252d β** everywhere; `beta_diagnostic.py`'s faster βs live only
  inside this read-only tool. Never let the diagnostic leak into a sensor path.
- The crisis gate stays **absolute, not baseline-relative** — market-wide correlation is a fragility
  gauge whose intrinsic level *is* the signal. The aging monitor's headroom is the sanctioned way to
  detect drift; the fix is a deliberate human re-freeze, never a rolling window.

## See also

- Spec §10 (test 5 / 5b / 5c) and §4a in `docs/prospector-v1-spec-rev14-2026-07-08.md`;
  `ARCHITECTURE.md` §2 (module map) and §5 (the backtest + acceptance gate).
- `docs/decisions/2026-07-02-stress-gate-recalibration.md` (absolute 0.85, crisis-only; the
  aging-drift monitor) and `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` (the box A/B/C
  diagnostic and why it is never wired to the sensor).
