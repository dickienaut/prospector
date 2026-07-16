# `prospector/identity/` — the failed-resolution state machine

Every fund keys on its SEC series id (`S######`); a bare ticker is rejected at the write path
(spec §2, Identity CONTRACT). EDGAR's ticker→series map lags precisely for the brand-new and
weird funds — exactly the targets — so a failed resolution must never silently drop the fund.
This package is the retry-then-manual queue that guarantees it doesn't. Implements spec §2 (and
the §4c two-phase-launch intake). **Built.**

## Modules

- **`resolution.py`** — the `ResolutionMachine`. `register_launch()` is the launch sensor's
  two-phase per-candidate entry point: **phase one always** emits `launch.unverified` onto
  `_system` to nail the detection timestamp into the record *before* resolution (a launch
  timestamp cannot be backfilled); **phase two** resolves, keying on the *detected* series
  (`resolve_series`, the HECO/I1 identity rule) so a reused ticker can't pick the wrong fund.
  `run_retries()` is the daily pass the runner calls — successes self-heal, and past
  `identity.retry_days` a ticker escalates to the manual queue (the escalation is itself an
  event). `resolve_manual()` is the human path behind `pros identity resolve` (EDGAR-verified,
  no bypass flag in v1). `launch_lag()` computes the signed T(structural)→T(launch) lag,
  reading **only** the launch payload's `detected_at`.

## Important to know

- **Nothing evaporates.** The queue is the anti-silent-drop guarantee: every transition is an
  event (`resolution.failed`, `identity.resolved`, the completing `launch`). The
  `resolution_queue` table is a **working index** owned here on the shared connection — the
  events are the truth (registry.py's DDL stays frozen, vendored provenance).
- **Lag integrity (CONTRACT §4c).** All lag math uses the launch payload's `detected_at`, never
  resolution time — a fund that resolves nine days late still gets its day-one launch timestamp.
- Tickers are **display-only** attributes; the series id is the key.
- **Deferred:** the completing `launch` currently lands on `_system`. Routing it onto
  overlapping live leads (the corroboration reach-back + live cross-stream lag) happens in a
  separate pass (`launch_corroboration.py` / the §9d SOI-corroboration retry), not here. The
  module docstring still frames this routing as "the DEFINED next slice" — that predates the
  SOI resolver landing; treat `ARCHITECTURE.md` §9 as authoritative on what is wired.

## See also

- Spec §2 (identity / the queue) and §4c (two-phase launch, lag integrity) in
  `docs/prospector-v1-spec-rev15-2026-07-16.md`; `ARCHITECTURE.md` §6 (identity) and §9.
- `docs/decisions/2026-07-03-launch-sensor-capture-first.md`,
  `docs/decisions/2026-07-06-identity-integrity.md`.
