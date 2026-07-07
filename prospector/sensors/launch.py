"""Launch sensor — the consensus clock (spec §4c, milestone 4 · detection + recording).

New US-listed ETFs are the near-consensus stream: a fund packaging a thesis is a dated public
timestamp (Ben-David et al. 2023 — the people who *buy* that timestamp underperform; Prospector
only *reads* it). This module is the CAPTURE half — detection and two-phase recording — and it is
deliberately first, for a reason that is FORCED, not chosen:

    A launch timestamp cannot be backfilled. If you were not watching when a fund launched, that
    datum is gone forever. So the cadence backbone (`launch.unverified` -> `launch`, `detected_at`
    preserved) MUST run continuously from day one. The INTERPRETATION half — the corroboration
    hook that routes a launch onto overlapping live leads, yielding the live cross-stream lag —
    can follow later and thaw backward over the captured launch history. Capture now, interpret
    later: the same shape that resolved the discourse-stream and stress-gate questions.

DETECTION: diff two frozen `company_tickers_mf.json` snapshots (§3, freeze-the-substrate). A
`(symbol, seriesId)` pair present today and absent in the prior pull is a new registration
surfacing in the SEC's mutual-fund/ETF ticker map. Deterministic and offline: the runner (§9,
milestone 5+) freezes each daily pull and holds the prior one. Honest coarseness — absorbed
downstream, never hidden:
  - The MF map covers mutual funds AND ETFs, so this over-detects. `resolve_ticker`'s prospectus
    confirmation (§2) and the human filter downstream sort real emerging-tech ETFs from the rest,
    and every unverified detection lands on `_system`, keying no lead — over-detection is cheap and
    recorded, never a spawn.
  - The map can lag a brand-new fund by days; the retry-then-manual queue (`resolution.py`) absorbs
    the lag, and `detected_at` is nailed at detection, so a late resolution never moves the datum.
  - A reused ticker (the HECO case) surfaces as a NEW `(symbol, seriesId)` because the series id
    changed — correct, because everything downstream keys on the series id, never the ticker.
A precision pass — the raw 485 daily-index scan, and an etfdb name skim to fill `name_raw` — is a
deferred enrichment, not a correctness gap.

The two-phase RECORDING lives in `ResolutionMachine.register_launch` (`resolution.py`), which owns
the event emission, the resolve, and the retry queue. This module is the detector + per-day driver.

DEFERRED — the DEFINED next slice, not an open-ended "v-later" (see
`docs/decisions/2026-07-03-launch-sensor-capture-first.md`): the corroboration hook, and a launch's
concentration derived FROM ITS FIRST HOLDINGS (not prospectus prose) — built and jointly tested so
the hook is never shipped without the live input it consumes. Its named unblock is holdings ingest
(§4d, this milestone): holdings give the fund's actual sectors (ground truth — look-through is
truth, and HECO is the standing proof a *stated* identity can be categorically wrong), so
corroboration becomes a direct sector-set overlap with a live lead's baskets. Until that lands, the
live launch carries no concentration industries and the hook cannot honestly fire.
"""

from __future__ import annotations

from prospector.identity.resolution import ResolutionMachine


def _symbol_series(mf: dict) -> set[tuple[str, str]]:
    """The set of `(SYMBOL, seriesId)` pairs in a `company_tickers_mf.json` snapshot. Symbols are
    upper-cased for a stable diff; the map's fields are `[cik, seriesId, classId, symbol]`
    (see `edgar.mf_tickers`)."""
    idx = {f: i for i, f in enumerate(mf["fields"])}
    return {(str(row[idx["symbol"]]).upper(), str(row[idx["seriesId"]]))
            for row in mf["data"]}


def new_registrations(current: dict, prior: dict) -> list[tuple[str, str]]:
    """New `(symbol, seriesId)` pairs in `current` but not `prior` — the new-registration signal
    (§4c), sorted for a deterministic scan order. Both args are parsed `company_tickers_mf.json`
    maps; a first run with an empty `prior` would flag the whole universe, so the runner seeds the
    prior snapshot at deploy rather than scanning cold."""
    return sorted(_symbol_series(current) - _symbol_series(prior))


def scan(current: dict, prior: dict, machine: ResolutionMachine,
         now: str) -> dict[str, list[str]]:
    """One launch-scan pass: record every new `(symbol, seriesId)` via the machine's two-phase
    intake, stamping each with the SAME detection time `now` (one pass = one detection moment, so
    the whole day's launches share a timestamp). Returns `{'resolved': [...], 'queued': [...]}` —
    funds that resolved immediately vs. those parked in the retry-then-manual queue. The runner
    calls this daily with the freshly frozen MF snapshot and the prior one (§9)."""
    out: dict[str, list[str]] = {"resolved": [], "queued": []}
    for symbol, series_id in new_registrations(current, prior):
        # Thread the DETECTED series id (I1): resolution keys on it, never re-derives which series the
        # ticker means (matches[0] can pick wrong on a reused ticker — the HECO guarantee).
        status = machine.register_launch(symbol, name_raw=None, detected_at=now, series_id=series_id)
        out[status].append(symbol)
    return out
