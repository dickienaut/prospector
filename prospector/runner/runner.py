"""The M5 runner — the scheduled cadence entrypoint (spec §9). ONE invocation = ONE tick.

Everything through M4 is a pure function or a deferred pass waiting for a driver. This is that
driver: it invokes the deterministic sensors in the CONTRACT run order, on cadence, and renders
their output. It adds NO intelligence (spec CONTRACT) — all judgment lives in the sensors (facts)
and the human (verdicts). If a change here would make the runner *interpret* rather than
*sequence*, it belongs in a sensor or in the human's hands, not here.

Firewall (CONTRACT): the runner touches only its own store and its own notifier. It never reads
the detector's bucket or the portfolio config, never places/sizes/recommends a trade, and exposes
no run-now surface (cron invokes it; scheduling is M7). Statelessness (CONTRACT §9): the runner holds
nothing across ticks — all between-tick state is recovered from the fossil record (§9f), so two
cold runs over the same store produce identical events.

SCOPE — grown well past the thin spine. WIRED, in CONTRACT run order: config honesty (§9-1), the
§9a mf-tickers + sector-prices ingest, §4a xcorr (the PRIMARY live lead-spawner), §4c launch-
recording, the §9d deferred SOI-corroboration retry, and the §4d mandate-diff (§9c frozen-prior).
Remaining spec-cited SLOTS, each additive in its CONTRACT position:
  §4b dispersion + §9e shadow clock  — needs the holdings/constituent-price vertical (a later slice)
  §4d rebalance (holdings-diff)      — needs holdings ingest (same vertical)
  §10 real email sender              — NullNotifier here; the sender is a later slice

THE FOUR SUBTLE BITS (spec §9, "comment the why") — each encodes a CONTRACT that is not obvious
from the mechanics; they are marked inline where they live:
  #1 config-hash BEFORE any sensor       — acting on an un-fossilized config change is a hindsight hole
  #2 mandate prior from the FROZEN blob  — the intra-run accession-advance trap (§9c) [at the §4d slot]
  #3 deferred passes are CALLED WITH sectors, never assume them (§9d) [at the §4c corroboration slot]
  #4 shadow clock surfaces readiness, NEVER auto-promotes (§9e) [at the §4b dispersion slot]
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, timedelta

from prospector.config import check_config_honesty
from prospector.fold.fold import active_nonshadow, fold, state_changed
from prospector.fold.snapshots import SnapshotConfig, should_snapshot, write_snapshot
from prospector.identity.resolution import ResolutionMachine
from prospector.ingest.edgar import (SOI_AMBIGUOUS, SOI_ERROR, classify_soi_target,
                                     latest_prospectus, prospectus_history)
from prospector.ingest.holdings import (MembershipSnapshot, priceable_members, priced_coverage,
                                         weight_covering_members)
from prospector.ingest.prices import (CALENDAR_PER_TRADING_DAY, PriceIngestError, build_panel,
                                       guard_live_source, required_pull_start)
from prospector.ingest.prospectus import ProspectusIngest
from prospector.ingest.soi import SoiIngest
from prospector.runner.deps import RunnerDeps
from prospector.runner.runlog import RunLog, write_run_log
from prospector.sensors import dispersion as dispersion_sensor
from prospector.sensors import launch as launch_sensor
from prospector.sensors import mandate as mandate_sensor
from prospector.sensors import soi as soi_sensor
from prospector.sensors import xcorr as xcorr_sensor
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.launch_corroboration import (lead_sectors, pending_soi_resolution,
                                                     series_id_sectors)
from prospector.store.envelope import SYSTEM_LEAD, parse_ts
from prospector.store.fund_registry import FundRegistry

__all__ = ["run_tick"]


class _CountingStore:
    """Tallies appended event types for the run-log (§9g) and otherwise delegates to the wrapped
    EventStore. EVERY write path in the tick goes through it — config-honesty's append, the
    sensors' ResolutionMachine, the FundRegistry, and the snapshot fault sink — so the run-log's
    per-type counts are complete. It is not a store of its own: `__getattr__` forwards everything
    but `append`."""

    def __init__(self, inner, counts: Counter):
        self._inner = inner
        self._counts = counts

    def append(self, raw):
        written = self._inner.append(raw)
        self._counts[written.envelope.type] += 1
        return written

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _emit_fault(store, subsystem: str, message, now: str, faults: list, *, lead: str | None = None):
    """A SOFT fault (§9g): a per-unit failure is recorded on `_system` and the tick continues —
    one fund's 404 or one basket's degenerate matrix must not blind the others. Never raises: the
    fault surface itself must not abort the run (a fault while recording a fault is swallowed, so
    the dead-man push still fires)."""
    faults.append({"subsystem": subsystem, "message": str(message)})
    payload = {"subsystem": subsystem, "message": str(message)}
    if lead is not None:
        payload["lead"] = lead
    try:
        store.append({"ts": now, "lead": SYSTEM_LEAD, "type": "fault",
                      "payload": payload, "schema": 1})
    except Exception:  # recording a fault must never itself abort the tick
        pass


def _load_prior_mf_snapshot(layout, current_date: str):
    """§9f — the launch-diff's prior comes from the FOSSIL RECORD, never a side cache: the most
    recent frozen `mf_tickers` blob from a date strictly before today. Returns None on the first
    run ever, in which case the caller SEEDS (below) rather than flagging the whole universe as
    launches. There is no separate 'prior snapshot' table — the frozen ingest blob IS the state."""
    edgar_root = layout.root / "ingest" / "edgar"
    if not edgar_root.is_dir():
        return None

    def _prior(name: str) -> bool:
        # Parse the date rather than lexical-compare `name < current_date`: the ordering intent is
        # explicit and safe against any non-YYYY-MM-DD dir (which is simply not a prior snapshot, never
        # a crash). Lexical compare is correct only while every dir is ISO-dated — this makes it robust.
        try:
            return date.fromisoformat(name) < date.fromisoformat(current_date)
        except ValueError:
            return False

    dates = sorted(d.name for d in edgar_root.iterdir()
                   if d.is_dir() and _prior(d.name)
                   and (d / "company_tickers_mf.json").is_file())
    if not dates:
        return None
    return json.loads((edgar_root / dates[-1] / "company_tickers_mf.json").read_bytes())


def _compute_push(page_worthy: dict, faults: list) -> bool:
    """§10 CONTRACT — the push is pinned to a NON-SHADOW `fold.state_changed`: push iff some lead is
    non-shadow *after* a {status, shadow, verdict} change (that is exactly what `page_worthy` holds —
    see `_materialize_snapshots`), OR any fault (a fault ALWAYS pushes — the dead-man beats silence).

    §9e resolved a two-CONTRACT collision here: §8a says push on state change, §4b says a SHADOW lead
    is excluded from paging. Dispersion is the first shadow spawner, so a shadow spawn (`status:
    None->active`, `shadow: True`) IS a state change — but must NOT page. Gating on *non-shadow after
    the change* suppresses a shadow spawn/tick/revert (the fold leaves `shadow=True` on a revert),
    leaves every xcorr non-shadow path unchanged, and pages a future promotion (`shadow: true->false`)
    for free. The runlog's `changed_leads` still records ALL changes (the fossil stays whole); only the
    push decision reads the non-shadow subset. Ticks, silent corroborations, and queue mechanics
    produce no {status,shadow,verdict} delta at all, so they do not push — the anti-slot-machine cadence."""
    return bool(page_worthy) or bool(faults)


def run_tick(deps: RunnerDeps) -> RunLog:
    """Execute ONE cadence tick in the CONTRACT run order (§9):

        1. config honesty (fossilize a config change BEFORE any sensor)   [subtle bit #1]
        2. ingest            (§9a — mf-tickers + the sector-price panel)
        3. sensors §4a-§4d   (WIRED: xcorr §4a, dispersion §4b/§9e shadow, launch §4c, mandate §4d, SOI §9d)
        4. identity retries  (drain the retry-then-manual queue)
        5. capture           (no-op until M6)
        6. snapshots         (reactive materialization)
        7. push if state changed (§10 — through the notifier seam)

    Returns the RunLog (never raises for a sensor/ingest failure — those are soft faults; a
    backstop catch turns any escaped exception into a fault that STILL pushes and STILL writes the
    log, because a crashed run must be legible, not silent, §9g/§10)."""
    start = deps.monotonic()
    now = deps.now
    date = now[:10]
    counts: Counter = Counter()
    store = _CountingStore(deps.event_store, counts)  # every append flows through here (§9g counts)
    faults: list = []
    changed_leads: dict = {}
    page_worthy: dict = {}  # the NON-shadow subset of changed_leads — the push comparand (§4b/§9e)
    runlog = RunLog(run_id=deps.run_id, ts=now, date=date)

    try:
        # 1. CONFIG HONESTY FIRST (§9-run-order-1). SUBTLE BIT #1: a config change must be
        #    fossilized (`config.changed`, with the diff) BEFORE any sensor acts on it — acting on
        #    an un-fossilized change is a hindsight hole (a fold becomes uninterpretable across an
        #    unrecorded threshold move). If this step itself fails we do NOT run sensors (never act
        #    on an unchecked config), but snapshots + push below still run (the dead-man stays live).
        config_ok = True
        try:
            runlog.config_hash = deps.cfg_hash
            runlog.config_changed = check_config_honesty(
                deps.cfg, deps.cfg_hash, deps.registry, store.append, now)
        except Exception as e:  # a config-honesty failure is recorded, not silent
            config_ok = False
            _emit_fault(store, "config", e, now, faults)

        if config_ok:
            _run_sensors(deps, store, now, date, faults, runlog)

    except Exception as e:  # backstop: nothing above should escape, but a fault beats a crash (§9g)
        runlog.fatal = True  # snapshots + push still run in `finally` — a crash must not go silent.
        _emit_fault(store, "runner", e, now, faults)

    finally:
        # 6. SNAPSHOTS + 7. PUSH — always, even after a fault (the weekly dead-man depends on it).
        try:
            changed_leads, page_worthy = _materialize_snapshots(deps, store, now, faults)
        except Exception as e:  # a snapshot-phase failure still writes the run-log
            _emit_fault(store, "snapshots", e, now, faults)

        pushed = _compute_push(page_worthy, faults)  # §4b/§9e: NON-shadow changes (+ faults) page
        if pushed:
            # NullNotifier in the skeleton: records the intended push, sends nothing (§10). A send
            # failure is itself a soft fault — it must not lose the run-log.
            try:
                deps.notifier.push({"date": date, "run_id": deps.run_id,
                                    "changed_leads": changed_leads, "fault_count": len(faults)})
            except Exception as e:  # a send failure is a soft fault — it must not lose the run-log
                _emit_fault(store, "notify", e, now, faults)

        runlog.changed_leads = changed_leads
        runlog.pushed = pushed
        runlog.faults = list(faults)
        runlog.event_counts = dict(counts)
        runlog.elapsed_seconds = deps.monotonic() - start
        try:
            write_run_log(deps.layout, deps.registry, runlog)
        except Exception:  # best-effort telemetry; events/snapshots already landed
            pass

    return runlog


def _run_sensors(deps: RunnerDeps, store, now: str, date: str, faults: list, runlog: RunLog) -> None:
    """Run-order steps 2-5 (§9). WIRED: mf-tickers + §9a prices ingest, launch recording (§4c), the §4a
    xcorr spawner, the §4b dispersion shadow spawner (§9e — its own holdings/constituent-price vertical),
    the §4d mandate-diff accretion, and the §9d SOI-corroboration deferred pass. The CONTRACT run order
    stays visible in code (a test pins it). One ResolutionMachine (with a real FundRegistry) serves both
    launch and the retries, so a retry that resolves can complete its registry entry.

    N6: the prologue must not run outside a fault boundary — a bad value here (e.g. a non-integer
    `identity.retry_days` typo) would otherwise escape to run_tick's single backstop as ONE fatal `runner`
    fault and blind the ENTIRE sensor+ingest phase, the inverse of the per-unit granularity §9g promises.
    `retry_days` affects only the RETRY queue, never capture-first launch recording, so a bad value is a
    SCOPED `config` fault + fall back to the default — the phase still runs."""
    try:
        retry_days = int((deps.cfg.get("identity") or {}).get("retry_days", 10))
    except (TypeError, ValueError) as e:
        _emit_fault(store, "config.identity.retry_days", e, now, faults)
        retry_days = 10  # the retry pass degrades to the default; launch recording is unaffected
    machine = ResolutionMachine(
        deps.registry, store, FundRegistry(deps.layout, deps.registry, store),
        deps.edgar_client, retry_days=retry_days, clock=lambda: now)

    # 2. INGEST (§9a). Freeze-before-parse throughout: the EdgarClient's `persist` seam (wired in
    #    deps to layout.edgar_path) writes the raw body BEFORE mf_tickers() returns the parsed dict,
    #    and PriceIngest.pull freezes each price body before parse — so a corrupt body is still a
    #    postmortem artifact. A fetch failure is a SOFT fault (§9a), never a run-abort.
    #    SLOT: holdings / submissions ingest — follow-on verticals (prices now wired below).
    current_mf = None
    try:
        current_mf = deps.edgar_client.mf_tickers()
        runlog.ingests["mf_tickers"] = "ran"
    except Exception as e:  # a source failure is a soft fault (§9a), never a run-abort
        runlog.ingests["mf_tickers"] = "fault"
        _emit_fault(store, "ingest.mf_tickers", e, now, faults)

    # §9a PRICES ingest — WIRED. Build the sector-ETF correlation grid (config `universe`: the 11
    #    SPDRs + SPY) ONCE per tick — the shared price substrate the §4a xcorr spawner consumes (next
    #    slice) and, later, §4b dispersion, so both read one frozen grid. P1 GUARD: `guard_live_source`
    #    fails closed on an unverified Stooq (its `Close` is only ASSUMED adjusted; a wrong-return base
    #    is exactly P1's hazard). The panel is a built-and-frozen artifact with no consumer THIS slice.
    _panel = _build_sector_panel(deps, store, now, faults, runlog)  # consumed by _run_xcorr next slice

    # 3. SENSORS in CONTRACT sub-order (§4a -> §4b -> §4c -> §4d):
    #    §4a xcorr — WIRED (the runner's PRIMARY live lead-spawner). Consumes the sector-ETF panel
    #        built above + THIS tick's mf map (the authoritative ticker->series_id, since the seed
    #        universe is never 'launched' and so is never in the fund registry). A spawn is LIVE
    #        (shadow=false) -> it pages AND counts toward the §8a ceiling via active_nonshadow. The
    #        stress gate freezes the trigger on a crisis day (a would-be entry -> stressed departure
    #        on _system, never a spawn). Trigger state is reconstructed from the record (§9f).
    try:
        _run_xcorr(deps, store, now, faults, runlog, _panel, current_mf)
    except Exception as e:  # a batch-level failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["xcorr"] = "fault"
        _emit_fault(store, "sensor.xcorr", e, now, faults)
    #    §4b dispersion — WIRED (§9e). The runner's SECOND live spawner, in SHADOW (burn-in). SUBTLE
    #        BIT #4 lives here: the dispersion shadow clock surfaces burn-in readiness in the
    #        heartbeat/dashboard, but the runner NEVER auto-promotes shadow->paging — that is a human
    #        config flip that leaves a config.changed fossil (auto-promotion would re-trust survivor-
    #        biased calibration). Its own holdings/constituent-price vertical (membership from the LIVE
    #        SPDR feed, never the empty registry). A shadow spawn does not page (§9e push gate, above).
    try:
        _run_dispersion(deps, store, now, faults, runlog, current_mf)
    except Exception as e:  # a batch-level failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["dispersion"] = "fault"
        _emit_fault(store, "sensor.dispersion", e, now, faults)
    #    §4c launch     — WIRED.
    if current_mf is not None:
        try:
            prior_mf = _load_prior_mf_snapshot(deps.layout, date)  # §9f: from the frozen record
            if prior_mf is None:
                # First run ever: SEED. A cold diff against an empty prior would flag the entire
                # universe as launches (sensors/launch.py, spec §9a); today's map becomes the prior
                # (already frozen by the ingest above), and tomorrow's tick diffs against it.
                runlog.sensors["launch"] = "seeded"
            else:
                launch_sensor.scan(current_mf, prior_mf, machine, now)
                runlog.sensors["launch"] = "ran"
        except Exception as e:  # one sensor's failure is a soft fault, never a run-abort (§9g)
            runlog.sensors["launch"] = "fault"
            _emit_fault(store, "sensor.launch", e, now, faults)
    # §9d: the deferred SOI-corroboration retry pass — WIRED (SUBTLE BIT #3: a deferred pass is CALLED
    #      WITH its sectors, never assumes them; a not-yet (resolve_soi_target None) leaves the launch
    #      sectors_unresolved to re-attempt; it reaches back, preserving the original detected_at as T2).
    #      The holdings corroboration that first records `sectors_unresolved` is a separate §9a/§4c SLOT.
    try:
        _run_soi_corroboration(deps, store, now, faults, runlog, machine.fund_registry)
    except Exception as e:  # a batch-level failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["soi_corroboration"] = "fault"
        _emit_fault(store, "soi.corroboration", e, now, faults)
    # §4d mandate-diff — WIRED (SUBTLE BIT #2 / §9c): the diff's prior is the last FROZEN prospectus
    #      blob (`has_frozen`), never the registry `prospectus_accession` field — an identity pass earlier
    #      in THIS run may advance that field, so reading the prior from it would diff the new filing
    #      against itself and miss a real change. (Rebalance, the holdings-diff sibling, stays a SLOT — it
    #      needs holdings ingest, a separate vertical.)
    try:
        _run_mandate(deps, store, now, faults, runlog, machine.fund_registry)
    except Exception as e:  # a batch-level failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["mandate"] = "fault"
        _emit_fault(store, "mandate", e, now, faults)

    # 4. IDENTITY RETRIES (§9-run-order-4). Drain the retry-then-manual queue; nothing evaporates.
    try:
        machine.run_retries()
        runlog.sensors["identity_retries"] = "ran"
    except Exception as e:  # a retry-pass failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["identity_retries"] = "fault"
        _emit_fault(store, "identity.retries", e, now, faults)

    # 5. CAPTURE — no-op until M6 (§9-run-order-5). The slot exists now so M6 plugs in without
    #    reshaping the run order.
    runlog.sensors["capture"] = "slot"


def _build_sector_panel(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog):
    """§9a prices ingest — the sector-ETF correlation grid (config `universe`: the 11 SPDRs + SPY),
    the shared price substrate the §4a xcorr and (later) §4b dispersion spawner passes consume. Pull
    each ticker's adjusted closes from the LIVE primary source (config `prices.primary`), FREEZE
    before parse (§3, via the built `PriceIngest.pull`), and assemble the wide panel with `build_panel`.

    P1 GUARD (§3): `guard_live_source` fails closed when the live source is an unverified Stooq —
    `parse_stooq` only ASSUMES `Close` is adjusted, and an unadjusted close silently corrupts every
    return across a split/dividend (the base of the sensor stack). Yahoo (primary) reads `adjclose`.

    Granularity (§9g): the guard trip and each per-ticker fetch/parse failure (and an empty frame) are
    SOFT faults — recorded on `_system`, the column skipped, the pass continues; never a run-abort.
    Returns the panel, or None if the guard tripped or no ticker landed (the xcorr pass then records
    'skipped')."""
    uni = deps.cfg.get("universe") or {}
    tickers = list(uni.get("sectors") or [])
    if uni.get("market"):
        tickers.append(uni["market"])
    source = (deps.cfg.get("prices") or {}).get("primary", "yahoo")
    try:
        guard_live_source(source, deps.cfg)  # P1: refuse an unverified adjusted-close source, loud
    except PriceIngestError as e:
        runlog.ingests["prices"] = "fault"
        _emit_fault(store, "ingest.prices", e, now, faults)
        return None
    start = required_pull_start(now[:10], deps.cfg)
    end = now[:10]
    frames = []
    for t in tickers:
        try:
            frame = deps.price_ingest.pull(t, source, start, end)  # freeze-before-parse (§3)
            if frame.empty:  # a valid body with no rows contributes no column (never a fabricated one)
                _emit_fault(store, "ingest.prices", f"{t}: empty price frame (no rows)", now, faults)
                continue
            frames.append(frame)
        except Exception as e:  # one ticker's failure never blinds the grid (§9g)
            _emit_fault(store, "ingest.prices", f"{t}: {e}", now, faults)
    if not frames:
        runlog.ingests["prices"] = "skipped" if not tickers else "fault"
        return None
    panel = build_panel(frames)
    runlog.ingests["prices"] = "ran"
    return panel


_XCORR_TRIGGER_TYPES = ("lead.spawned", "xcorr.departure", "xcorr.tick", "xcorr.reverted")


def _universe_series_ids(cfg: dict, current_mf: dict | None) -> dict:
    """`{sector ticker -> SEC series id}` resolved from THIS tick's mf-tickers map — the authoritative
    `[cik, seriesId, classId, symbol]` feed already fetched for the launch diff, NOT the fund registry.
    Why not the registry: the seed universe is never 'launched', and `upsert` fires only on a resolved
    launch, so the 11 SPDRs are never registered there — reading it would leave xcorr permanently inert.
    xcorr keys its lead on series ids (§2/§5 CONTRACT), so this is the bridge that lets it spawn. SPY is
    deliberately excluded: it is a UIT with no series id and is only the β-strip market factor, never a
    pair member. A ticker that is absent or maps to >1 distinct series id (ambiguous) is skipped — refuse
    to guess (bounded, honest), never a wrong key."""
    if not current_mf:
        return {}
    try:
        idx = {f: i for i, f in enumerate(current_mf["fields"])}
        si, sy = idx["seriesId"], idx["symbol"]
    except (KeyError, TypeError):
        return {}
    by_ticker: dict[str, set] = {}
    for row in current_mf.get("data", []):
        by_ticker.setdefault(str(row[sy]).upper(), set()).add(str(row[si]))
    out: dict[str, str] = {}
    for ticker in (cfg.get("universe") or {}).get("sectors", []):
        sids = by_ticker.get(str(ticker).upper())
        if sids and len(sids) == 1:
            out[ticker] = next(iter(sids))
    return out


def _xcorr_last_event_types(deps: RunnerDeps) -> dict:
    """§9f — reconstruct each xcorr lead's Schmitt-state SOURCE from the fossil record: `{lead_id ->
    its last TRIGGER-relevant event type}`. Read straight from the registry (the same events the fold
    reads, ORDER BY ts, event_id), never a side cache. Only trigger-vocabulary events count
    (`lead.spawned`/`xcorr.*`), so a later corroboration/verdict on the lead cannot be misread as an
    active departure (the schmitt contract). A pair that never spawned has no lead here -> `None` ->
    quiet, so it can enter cleanly."""
    out: dict[str, str | None] = {}
    for lead in deps.registry.all_leads():
        if lead == SYSTEM_LEAD or not str(lead).startswith("xcorr-"):
            continue
        last = None
        for r in deps.registry.events_for_lead(lead):
            if r["type"] in _XCORR_TRIGGER_TYPES:
                last = r["type"]
        out[lead] = last
    return out


def _run_xcorr(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog, panel,
               current_mf: dict | None) -> None:
    """§4a xcorr — the runner's PRIMARY live lead-spawner. Drive `xcorr_sensor.scan` over the sector-ETF
    panel built this tick: resolve the universe tickers -> series ids from the mf map
    (`_universe_series_ids` — the lead keys on series ids, §2/§5), reconstruct each pair's Schmitt state
    from the record (`_xcorr_last_event_types`, §9f), and step one tick. A spawn is LIVE (shadow=false):
    it pages and counts toward the §8a ceiling via `active_nonshadow`, no extra code. No panel (prices
    ingest faulted / empty) -> 'skipped', honestly (xcorr cannot run without a warmed price grid). A
    batch failure (e.g. the panel lacks the market column) escapes to the caller's soft-fault boundary."""
    if panel is None or getattr(panel, "empty", True):
        runlog.sensors["xcorr"] = "skipped"  # no prices this tick — honest, not a silent no-op
        return
    ticker_to_series_id = _universe_series_ids(deps.cfg, current_mf)
    last_event_types = _xcorr_last_event_types(deps)
    xcorr_sensor.scan(panel, ticker_to_series_id, deps.cfg, now, last_event_types, store.append)
    runlog.sensors["xcorr"] = "ran"


_DISPERSION_TRIGGER_TYPES = ("lead.spawned", "dispersion.tick", "dispersion.reverted")


def _dispersion_pull_start(as_of_date: str, cfg: dict) -> str:
    """Earliest ISO pull date for a fully-warmed dispersion departure-z: the constituent-correlation
    window (`dispersion.window_days`) plus the Q baseline (`dispersion.baseline_days`), sized to
    CALENDAR days with the same 1.5 buffer prices.py uses. Reads dispersion's OWN windows (§4b), NEVER
    `cfg['windows']` (that is xcorr's 567-day beta-strip chain — reusing `required_pull_start` here
    would silently couple dispersion's history depth to xcorr's config)."""
    d = cfg["dispersion"]
    trading = int(d["baseline_days"]) + int(d["window_days"])          # 252 + 63 = 315 at defaults
    days = math.ceil(trading * CALENDAR_PER_TRADING_DAY)
    return (date.fromisoformat(as_of_date) - timedelta(days=days)).isoformat()


def _tiingo_symbol(ticker: str) -> str:
    """SPDR holdings carry class-share tickers in DOT form (BRK.B); Tiingo's symbol path wants DASH
    form (BRK-B). Normalize HERE, at the constituent-pull seam — NEVER in the shared price URL builder
    (a Tiingo-only quirk must not leak onto the yahoo/stooq sector-ETF path). A genuinely unresolvable
    symbol still hits Tiingo, 404s, and is dropped from the panel (a coverage gap, never a guess).
    PRIMARY-SOURCE GATE (§9e, WIDENED): the caller (`_run_dispersion`) now excludes FOREIGN (non-USD) and
    cash/placeholder lines at the membership boundary via `priceable_members`, so a foreign local ticker
    that COLLIDES with a US symbol (`ENR`=Siemens abroad, also NYSE:Energizer) does NOT reach here to
    silently return the wrong series. Before the live run, confirm on real XLF/XLC/XLY files that dual-class
    (BRK.B, GOOG/GOOGL, FOX/FOXA) AND foreign/cash lines are handled — the dual-class dot/dash check alone
    would NOT catch `ENR` (a clean-looking symbol pointing at the wrong company is a different failure
    mode). See docs/decisions/2026-07-10-9e-constituent-symbol-resolution.md."""
    return ticker.strip().upper().replace(".", "-")


def _dispersion_last_event_types(deps: RunnerDeps) -> dict:
    """§9f — reconstruct each dispersion lead's Schmitt-state SOURCE from the fossil record: `{lead_id
    -> its last TRIGGER-relevant event type}`. Leads keyed `disp-` (`dispersion_lead_id`), read straight
    from the registry (never a side cache), filtered to the trigger vocabulary. Dispersion has NO
    `.departure` event (spawn/tick -> active, reverted -> quiet), so the set is spawn/tick/reverted.
    Mirrors `_xcorr_last_event_types`; a basket that never spawned has no lead here -> None -> quiet."""
    out: dict[str, str | None] = {}
    for lead in deps.registry.all_leads():
        if lead == SYSTEM_LEAD or not str(lead).startswith("disp-"):
            continue
        last = None
        for r in deps.registry.events_for_lead(lead):
            if r["type"] in _DISPERSION_TRIGGER_TYPES:
                last = r["type"]
        out[lead] = last
    return out


def _build_constituent_panel(deps: RunnerDeps, members, source: str, start: str, end: str):
    """Pull each constituent's adjusted closes BY TICKER (Tiingo is queried by symbol), then RE-KEY the
    panel columns to the constituent IDENTIFIER (CUSIP) — the dispersion sensor CONTRACT: the panel keys
    on the stable identifier (`membership.identifiers()`), the ticker is only the lookup attribute (HECO
    one level down). Re-key by overwriting each tidy frame's `ticker` column to its CUSIP BEFORE
    `build_panel`, so BOTH the columns AND `attrs['sources']` come out identifier-keyed (a post-hoc
    `.rename()` would leave `attrs['sources']` ticker-keyed -> a silent source-lookup miss). The frozen
    price fossil stays keyed by the real Tiingo symbol (freeze happens inside `pull`, before the re-key).

    `members` is an ordered iterable of `(ticker, identifier)` pairs — CUSIP-keyed FROM THE START (§9e
    Option 2), NOT a `{ticker: identifier}` dict: SSGA writes cash lines with a non-unique `-` ticker, and
    a dict would collapse two of them to one key, silently dropping a CUSIP. A list of pairs preserves
    every CUSIP, and `build_panel` FAULTS on a genuinely duplicate CUSIP rather than fabricate.

    Per-constituent granularity: a constituent whose pull fails is DROPPED (a coverage gap — counted by
    absence, never an 8-names-404 fault storm); `corr_matrix_at` drops any name lacking a full window and
    `min_constituents` guards degeneracy, so a partial panel degrades honestly. Returns the re-keyed
    panel, or None if no constituent landed (the caller then SKIPS the basket, distinct from a
    holdings-fetch failure which FAULTS it — a broken feed is worth surfacing, a price gap is not)."""
    frames = []
    for ticker, identifier in members:                     # membership order (weight desc) preserved
        try:
            frame = deps.price_ingest.pull(_tiingo_symbol(ticker), source, start, end)
            if frame.empty:
                continue
            frame = frame.copy()
            frame["ticker"] = identifier                   # re-key BEFORE build_panel (columns + attrs)
            frames.append(frame)
        except Exception:                                  # one constituent's gap never faults the basket
            continue
    if not frames:
        return None
    return build_panel(frames)


def _run_dispersion(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog,
                    current_mf: dict | None) -> None:
    """§4b dispersion — the runner's SECOND live spawner, SHADOW-wired (§9e burn-in). For each of the 11
    SPDR baskets resolvable THIS tick (`_universe_series_ids` from the mf map — never the empty registry,
    the trap that would leave it permanently inert): pull the basket's holdings THIS tick (freeze-before-
    parse), truncate to the weight-covering membership (0.90), FILTER to the constituents priceable by a
    bare US ticker (§9e: drop foreign/cash/placeholder lines — never a silent wrong series; excluded
    weight becomes a reported coverage gap), pull those prices BY TICKER, re-key the panel to CUSIP
    identifiers (the sensor CONTRACT), reconstruct Schmitt state from the record (§9f),
    and drive `dispersion.scan` with `tick_due=True` (mirrors xcorr's per-run tick — daily when the runner
    runs daily; `dispersion.tick_cadence_days` stays advisory until M7 owns the schedule). A spawn is
    `shadow=true`: it starts the burn-in clock and `active_nonshadow` excludes it from the ceiling and
    corroboration, while the §9e push gate keeps a shadow-only change from paging.

    Soft-fault granularity (§9g): the per-basket try/except makes a HOLDINGS fetch/parse failure a
    per-basket FAULT (a broken feed for an expected basket must surface) that never aborts the run; a
    basket with no priceable constituents is SKIPPED (a coverage gap, honest — distinct from a broken
    feed, never a guess). `runlog.sensors['dispersion']` is 'ran' (>=1 basket drove the sensor) or
    'skipped' (none resolvable / none priceable) — never a silent no-op."""
    ticker_to_series_id = _universe_series_ids(deps.cfg, current_mf)
    if not ticker_to_series_id:
        runlog.sensors["dispersion"] = "skipped"  # no resolvable baskets this tick — honest
        return
    dcfg = deps.cfg["dispersion"]
    cov = float(dcfg["weight_coverage"])
    source = (deps.cfg.get("prices") or {}).get("primary", "yahoo")
    try:
        # P1 (§3): the SAME fail-closed wall the sector panel enforces — NEVER pull/freeze constituent
        # prices from a source whose adjusted close is unverified (`parse_stooq` only ASSUMES Close is
        # adjusted; an unadjusted close silently corrupts every constituent return across a split). Skip
        # the whole pass loudly rather than fabricate the substrate the dispersion correlation reads.
        guard_live_source(source, deps.cfg)
    except PriceIngestError as e:
        runlog.sensors["dispersion"] = "skipped"
        _emit_fault(store, "sensor.dispersion", e, now, faults)
        return
    date_ = now[:10]
    start = _dispersion_pull_start(date_, deps.cfg)
    last_event_types = _dispersion_last_event_types(deps)
    ran_any = False
    for ticker, series_id in ticker_to_series_id.items():
        lead_id = dispersion_lead_id(series_id)
        try:
            frame = deps.holdings_ingest.pull(series_id, ticker)      # freeze-before-parse (§3)
            total_weight = float(frame["weight"].sum())               # denominator for honest coverage
            members, _ = weight_covering_members(frame, cov)          # top-`cov` by weight (the O(n^2) bound)
            # §9e constituent-symbol resolution: keep only lines priceable by a BARE US ticker BEFORE the
            # pull — drop foreign (non-USD) listings (the `ENR`=Siemens/Energizer collision that silently
            # returns the WRONG series) and cash/derivative/placeholder lines. Excluded weight is a reported
            # coverage gap, never a silent wrong substrate. docs/decisions/2026-07-10-9e-constituent-symbol-resolution.md.
            priceable = priceable_members(members)
            if not priceable:
                continue  # membership parsed but nothing priceable by a US ticker — a coverage gap, skip
            # CUSIP-keyed from the start (Option 2): a `{ticker: id}` dict collapses two non-unique tickers
            # (SSGA writes cash lines as `-`) into one key, silently dropping a CUSIP; a list of pairs keeps
            # every CUSIP (and build_panel FAULTS on a genuinely duplicate CUSIP, never fabricates).
            panel = _build_constituent_panel(
                deps, [(m["ticker"], m["identifier"]) for m in priceable], source, start, date_)
            if panel is None:
                continue  # no constituent priced — SKIP this basket (coverage gap, never a guess)
            # Coverage honesty (§9e): report the fraction of TOTAL basket weight that ACTUALLY priced
            # (after exclusions AND per-constituent price-pull drops), not the pre-pull top-`cov` sum — so
            # the burn-in Q is trustworthy (you know what universe it was computed on). `members` on the
            # snapshot is the priceable set (the intended price universe); the payload reads name/weight
            # from it by the panel's CUSIP columns, so a 404-dropped name simply does not appear.
            coverage_actual = priced_coverage(priceable, set(panel.columns), total_weight)
            membership = MembershipSnapshot(series_id=series_id, ticker=ticker, as_of=date_,
                                            source="spdr", members=priceable, coverage_target=cov,
                                            coverage_actual=coverage_actual)
            dispersion_sensor.scan(series_id, ticker, membership, panel, deps.cfg, now,
                                   last_event_types.get(lead_id), store.append, tick_due=True)
            ran_any = True
        except Exception as e:  # one basket's failure (holdings feed / parse) never blinds the others (§9g)
            _emit_fault(store, "sensor.dispersion", f"{ticker}: {e}", now, faults, lead=lead_id)
    runlog.sensors["dispersion"] = "ran" if ran_any else "skipped"


def _lead_context(deps: RunnerDeps, fund_registry: FundRegistry) -> tuple[dict, list]:
    """The shared corroboration/audit context: the sector-ETF universe tickers resolved to series_ids
    (via the registry), and the currently ACTIVE (non-shadow) lead ids (folded from the record — §9f).
    Used by the §9d SOI overlap and the §4d mandate routing (both forward-hash the universe against the
    active leads). Returns `(ticker_to_series_id, active_lead_ids)`; either may be empty (nothing
    registered / no live lead), which the callers handle honestly."""
    ticker_to_series_id: dict[str, str] = {}
    for ticker in (deps.cfg.get("universe") or {}).get("sectors", []):
        entry = fund_registry.by_ticker(ticker)
        if entry is not None:
            ticker_to_series_id[ticker] = entry.series_id
    active_ids = [s["lead"] for s in active_nonshadow(
        fold(deps.registry.events_for_lead(lead))
        for lead in deps.registry.all_leads() if lead != SYSTEM_LEAD)]
    return ticker_to_series_id, active_ids


def _active_lead_sectors(deps: RunnerDeps, fund_registry: FundRegistry) -> dict:
    """`{active lead_id -> its sector set}` for the corroboration overlap (§4d forward-hash): the
    `_lead_context` universe bridged to GICS sectors (config `sector_map`), `lead_sectors()` over the
    active leads. Returns {} when the universe isn't resolved yet or no leads are active — `soi.scan`
    then records `dormant_no_match` honestly (the overlap coverage is bounded by the xcorr/dispersion
    sensors, their own SLOTs)."""
    ticker_to_series_id, active_ids = _lead_context(deps, fund_registry)
    s2sec = series_id_sectors(deps.cfg.get("sector_map") or {}, ticker_to_series_id)
    return lead_sectors(list(ticker_to_series_id.values()), s2sec, active_ids)


def _last_frozen_prospectus(prospectus: ProspectusIngest, series_id: str, subs: dict,
                            current_accession: str) -> str | None:
    """The §9c mandate prior: the most-recent prospectus filing we hold FROZEN that isn't the current
    one — sourced from the blob store (`has_frozen`), NEVER the registry `prospectus_accession` field
    (an identity pass earlier in THIS run may have advanced that field to the new filing, so reading the
    prior from it would diff the new filing against itself and miss a real change). None if we hold no
    prior frozen (mandate.scan then baselines the current)."""
    for f in prospectus_history(subs):  # newest-first
        if f["accession"] != current_accession and prospectus.has_frozen(series_id, f["accession"]):
            return f["accession"]
    return None


def _run_mandate(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog,
                 fund_registry: FundRegistry) -> None:
    """§4d mandate-diff on cadence + the §9c frozen-prior invariant (SUBTLE BIT #2). For each registered
    (watched) fund: fetch submissions, take the latest prospectus (current) and — as the prior — the
    last FROZEN prospectus from the blob store (`_last_frozen_prospectus`, NEVER the registry field,
    §9c). `mandate.scan` freezes the current (freeze-before-diff), diffs the principal-investment-
    strategy section against the frozen prior, and routes `mandate.changed` (a SILENT corroboration onto
    the live leads it touches, else `_system`) or a `fault` on unreliable extraction — never a wrong
    change (a false `mandate.changed` is worse than a missed one). Per-fund failure is a soft fault
    (§9g); the pass goes on. SILENT (§10): `mandate.changed` never pushes; the human adjudicates
    cosmetic-vs-substantive.

    This runs REAL execution from day one — a baseline on first sight, a diff once a fund files a new
    prospectus across cadences — self-sufficient (records on `_system` even with no live lead). The
    holdings-diff sibling (rebalance) stays a SLOT: it needs holdings ingest, a separate vertical."""
    prospectus = ProspectusIngest(deps.layout, deps.edgar_client)
    ticker_to_series_id, active_ids = _lead_context(deps, fund_registry)
    universe_ids = list(ticker_to_series_id.values())
    mandate_cfg = deps.cfg.get("mandate") or {}
    for entry in fund_registry.all_funds():
        try:
            subs = deps.edgar_client.submissions(int(entry.cik))
            cur = latest_prospectus(subs)
            if cur is None:
                continue  # no prospectus-family filing on record for this fund
            prior = _last_frozen_prospectus(prospectus, entry.series_id, subs, cur["accession"])
            mandate_sensor.scan(entry.series_id, entry.ticker_current, int(entry.cik),
                                cur["accession"], cur["primary_doc"], prior,
                                universe_ids, active_ids, prospectus, mandate_cfg, now, store.append)
        except Exception as e:  # one fund's failure never blinds the others (§9g)
            _emit_fault(store, "mandate", e, now, faults)
    runlog.sensors["mandate"] = "ran"


def _run_soi_corroboration(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog,
                           fund_registry: FundRegistry) -> None:
    """§9d — the deferred SOI-corroboration retry pass (spec §9b/§9d; SUBTLE BIT #3). Enumerate the
    `sectors_unresolved` launches from the FOLD (§9f — the same single-source enumeration as active
    leads, never a side 'pending' table), and for each within the retry horizon: look up its registry
    entry (cik + fund-name anchor), resolve its latest SOI coordinates (`resolve_soi_target`, the
    step-2 machinery), and drive `sensors/soi.scan` — which reaches back preserving the original
    `detected_at` as T2, so the lag measures to detection, not to when the SOI arrived. Discipline:
      - CALLED WITH the SOI-derived sectors, never assuming they exist: `resolve_soi_target` returns
        None when the SOI isn't indexed yet or its exhibit is ambiguous (fault) — a NOT-YET, so the
        launch stays `sectors_unresolved` and is re-attempted next cycle; the run continues.
      - a per-launch failure is a SOFT fault (§9g): recorded, skipped, the pass goes on.
      - SILENT (§10): the emitted `launch`/`match` accretions never push; if an accretion changes a
        real lead's {status,shadow,verdict}, the step-6 snapshot re-fold catches it in this same tick.
    Coverage is bounded, honestly (the mechanism is what lands here): the `sectors_unresolved` input is
    produced by the holdings corroboration pass (a separate §9a/§4c SLOT), the overlap needs live
    xcorr/dispersion leads (their own SLOTs), and the fund-block anchor is the registry entry's name —
    live yield is gated on those, exactly like SPDR-only holdings coverage.

    No weekly cadence gate yet (the runner is cadence-agnostic; `schedule.weekly_day` is M7): §9d
    attempts each pending launch every tick, bounded by the retry horizon. Throttling the SOI-heavy
    fetch to weekly is an M7 scheduling concern, not a correctness one."""
    horizon = float((deps.cfg.get("corroboration") or {}).get("retry_horizon_days", 180))
    # Work-list from the fold (§9f): every `launch` event across all leads, with event_id for the
    # (ts, event_id) total order (read_lead's Envelope drops event_id, so read the rows directly).
    launch_events = [
        {"ts": r["ts"], "event_id": r["event_id"], "payload": json.loads(r["payload"])}
        for lead in deps.registry.all_leads()
        for r in deps.registry.events_for_lead(lead, "launch")]
    pending = pending_soi_resolution(launch_events, now, horizon)
    if not pending:
        runlog.sensors["soi_corroboration"] = "ran"  # ran, nothing pending (honest: not a 'slot')
        return
    soi = SoiIngest(deps.layout)
    active = _active_lead_sectors(deps, fund_registry)
    for launch in pending:
        try:
            entry = fund_registry.get(launch["series_id"])
            if entry is None:
                continue  # no registry entry (cik/anchor) yet -> stays pending, re-attempted
            target, reason = classify_soi_target(int(entry.cik), deps.edgar_client)
            if target is None:
                # N8: a genuine NOT-YET stays silent (re-attempt next cycle); an AMBIGUOUS exhibit or an
                # ERROR is a FAULT — the filing IS there but unresolvable, so it must surface ONCE for
                # manual review, not silently re-fetch every tick for 180 days (nor mask a real bug).
                if reason in (SOI_AMBIGUOUS, SOI_ERROR):
                    _emit_fault(store, f"soi.corroboration.{reason}",
                                f"SOI target unresolvable ({reason}) for {launch['series_id']} "
                                f"(cik {entry.cik}) — surface for manual review",
                                now, faults, lead=launch.get("lead"))
                continue  # not-yet OR surfaced-fault: the launch stays sectors_unresolved this tick
            soi_sensor.scan(
                launch, target.accession, entry.name, active, soi, deps.cfg, now, store.append,
                fetch_body=lambda t=target: deps.edgar_client.filing_text(
                    t.cik, t.accession, t.primary_doc))
        except Exception as e:  # one launch's failure never blinds the others (§9g)
            _emit_fault(store, "soi.corroboration", e, now, faults)
    runlog.sensors["soi_corroboration"] = "ran"


def _materialize_snapshots(deps: RunnerDeps, store, now: str, faults: list) -> tuple[dict, dict]:
    """Run-order step 6 (§9): re-fold every real lead and materialize on the reactive cadence
    (`should_snapshot` — immediate on a state change, dense while active, weekly floor otherwise).
    Returns `(changed_leads, page_worthy)`: `changed_leads` = {lead: [changed fields]} for the WHOLE
    record (the runlog + run-summary keep every change, shadow included — the fossil stays honest);
    `page_worthy` = the subset whose lead is NON-shadow AFTER the change — the §10 push comparand
    (§4b/§9e: a shadow-only change is recorded but never pages). `_system` is infra, not a lead — its
    events fold into the run-log/queue, never a lead snapshot.

    The prior state for the state-change comparison is read from the lead's LAST snapshot (before
    this tick writes a new one), so `state_changed(prior, new)` is honest. A snapshot divergence is
    a SOFT fault (fault_sink=store.append), not a run-abort; one lead's failure never blinds the
    others (§9g)."""
    snap_cfg = SnapshotConfig.from_cfg(deps.cfg.get("snapshots") or {})
    now_dt = parse_ts(now)
    changed_leads: dict = {}
    page_worthy: dict = {}
    for lead in deps.registry.all_leads():
        if lead == SYSTEM_LEAD:
            continue
        try:
            new_state = fold(deps.registry.events_for_lead(lead))
            prior_row = deps.registry.latest_snapshot(lead)
            prior_state = None
            last_ts = None
            if prior_row is not None:
                last_ts = prior_row["ts"]
                prior_state = json.loads(
                    (deps.layout.root / prior_row["file_path"]).read_text(encoding="utf-8"))
                prior_state.pop("reason", None)  # the reason is snapshot metadata, not fold state
            changed = state_changed(prior_state, new_state)  # §10's single arbiter
            if changed:
                changed_leads[lead] = changed
                # §4b/§9e: a shadow lead's change is recorded above but is NOT page-worthy. Gate on the
                # NEW state's shadow (the fold leaves shadow=True on a revert, and a promotion ends
                # shadow=False -> it pages) — see _compute_push.
                if not new_state.get("shadow", False):
                    page_worthy[lead] = changed
            decision = should_snapshot(new_state, last_ts, changed, now_dt, snap_cfg)
            if decision.save:
                write_snapshot(deps.layout, deps.registry, lead, new_state, decision.reason, now,
                               fault_sink=store.append)
        except Exception as e:  # one lead's failure never blinds the others (§9g)
            _emit_fault(store, "snapshot", e, now, faults, lead=lead)
    return changed_leads, page_worthy
