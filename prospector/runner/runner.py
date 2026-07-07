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

SCOPE — this is the THIN SPINE (build-order step 1). It gets the run order, the invariants, the
run-log, the exception granularity, and the snapshot/push machinery right, proven end to end
through ONE real vertical: launch-recording (§4c). Every other sensor and all genuinely-new logic
are explicit, spec-cited SLOTS filled in follow-on slices:
  §4a xcorr, §4b dispersion, §4d rebalance/mandate         — sensor SLOTS (steps 2-3)
  §9b SOI live-fetch, §9d deferred corroboration/SOI retry  — deferred-pass SLOTS (steps 2-3)
  §9c mandate frozen-prior, §9e shadow clock                — invariants noted at their slots
  §10 real email sender                                     — NullNotifier here; sender is step 4

THE FOUR SUBTLE BITS (spec §9, "comment the why") — each encodes a CONTRACT that is not obvious
from the mechanics; they are marked inline where they live:
  #1 config-hash BEFORE any sensor       — acting on an un-fossilized config change is a hindsight hole
  #2 mandate prior from the FROZEN blob  — the intra-run accession-advance trap (§9c) [at the §4d slot]
  #3 deferred passes are CALLED WITH sectors, never assume them (§9d) [at the §4c corroboration slot]
  #4 shadow clock surfaces readiness, NEVER auto-promotes (§9e) [at the §4b dispersion slot]
"""

from __future__ import annotations

import json
from collections import Counter

from prospector.config import check_config_honesty
from prospector.fold.fold import active_nonshadow, fold, state_changed
from prospector.fold.snapshots import SnapshotConfig, should_snapshot, write_snapshot
from prospector.identity.resolution import ResolutionMachine
from prospector.ingest.edgar import resolve_soi_target
from prospector.ingest.soi import SoiIngest
from prospector.runner.deps import RunnerDeps
from prospector.runner.runlog import RunLog, write_run_log
from prospector.sensors import launch as launch_sensor
from prospector.sensors import soi as soi_sensor
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
    dates = sorted(d.name for d in edgar_root.iterdir()
                   if d.is_dir() and d.name < current_date
                   and (d / "company_tickers_mf.json").is_file())
    if not dates:
        return None
    return json.loads((edgar_root / dates[-1] / "company_tickers_mf.json").read_bytes())


def _compute_push(changed_leads: dict, faults: list) -> bool:
    """§10 CONTRACT — the push is pinned to `fold.state_changed`: push iff some lead's
    {status, shadow, verdict} changed (that is exactly what `changed_leads` holds), OR any fault
    (a fault ALWAYS pushes — the dead-man beats silence). Ticks, silent corroborations
    (rebalance / mandate.changed / launch accretion), and queue mechanics produce NO
    {status,shadow,verdict} delta, so they do not push — the anti-slot-machine cadence, mechanical."""
    return bool(changed_leads) or bool(faults)


def run_tick(deps: RunnerDeps) -> RunLog:
    """Execute ONE cadence tick in the CONTRACT run order (§9):

        1. config honesty (fossilize a config change BEFORE any sensor)   [subtle bit #1]
        2. ingest            (§9a — thin spine: mf-tickers only)
        3. sensors §4a-§4d   (thin spine: launch-recording WIRED; the rest are SLOTS)
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
            changed_leads = _materialize_snapshots(deps, store, now, faults)
        except Exception as e:  # a snapshot-phase failure still writes the run-log
            _emit_fault(store, "snapshots", e, now, faults)

        pushed = _compute_push(changed_leads, faults)
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
    """Run-order steps 2-5 (§9). Thin spine: mf-tickers ingest + launch-recording (§4c) are WIRED;
    the structural (§4a/§4b) and accretion (§4d) sensors and the deferred passes (§9d) are SLOTS in
    their CONTRACT positions, so follow-on wiring is additive and the order stays visible in code
    (a test pins it). One ResolutionMachine (with a real FundRegistry) serves both launch and the
    retries, so a retry that resolves can complete its registry entry."""
    retry_days = int((deps.cfg.get("identity") or {}).get("retry_days", 10))
    machine = ResolutionMachine(
        deps.registry, store, FundRegistry(deps.layout, deps.registry, store),
        deps.edgar_client, retry_days=retry_days, clock=lambda: now)

    # 2. INGEST (§9a). Thin spine drives only mf-tickers (the launch input). Freeze-before-parse:
    #    the EdgarClient's `persist` seam (wired in deps to layout.edgar_path) writes the raw body
    #    BEFORE mf_tickers() returns the parsed dict, so a corrupt body is still a postmortem
    #    artifact. A fetch failure is a SOFT fault (§9a), never a run-abort.
    #    SLOT: prices / holdings / submissions ingest — follow-on verticals.
    current_mf = None
    try:
        current_mf = deps.edgar_client.mf_tickers()
        runlog.ingests["mf_tickers"] = "ran"
    except Exception as e:  # a source failure is a soft fault (§9a), never a run-abort
        runlog.ingests["mf_tickers"] = "fault"
        _emit_fault(store, "ingest.mf_tickers", e, now, faults)

    # 3. SENSORS in CONTRACT sub-order (§4a -> §4b -> §4c -> §4d):
    #    §4a xcorr      — SLOT (follow-on).
    #    §4b dispersion — SLOT (follow-on). SUBTLE BIT #4 lives here: the dispersion shadow clock
    #        (§9e) surfaces burn-in readiness in the heartbeat/dashboard, but the runner NEVER
    #        auto-promotes shadow->paging — that is a human config flip that leaves a config.changed
    #        fossil (auto-promotion would re-trust survivor-biased calibration).
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
    #    §4d rebalance / mandate — SLOT. SUBTLE BIT #2 (mandate, §9c): the diff's prior is the last
    #        FROZEN prospectus blob, never the registry `prospectus_accession` field — an identity
    #        pass earlier in THIS run may advance that field, so reading the prior from it would
    #        diff against a "prior" that was never actually frozen. Source from the blob store.

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


def _active_lead_sectors(deps: RunnerDeps, fund_registry: FundRegistry) -> dict:
    """`{active lead_id -> its sector set}` for the corroboration overlap (§4d forward-hash), assembled
    live: resolve the sector-ETF universe tickers to series_ids via the registry, bridge to GICS
    sectors (config `sector_map`), and `lead_sectors()` over the ACTIVE (non-shadow) leads. Returns {}
    when the universe isn't resolved yet or no leads are active — `soi.scan` then records
    `dormant_no_match` honestly (there is simply no live lead to overlap; the overlap coverage is
    bounded by the xcorr/dispersion sensors, which are their own SLOTs)."""
    universe = deps.cfg.get("universe") or {}
    sector_map = deps.cfg.get("sector_map") or {}
    ticker_to_series_id: dict[str, str] = {}
    for ticker in universe.get("sectors", []):
        entry = fund_registry.by_ticker(ticker)
        if entry is not None:
            ticker_to_series_id[ticker] = entry.series_id
    s2sec = series_id_sectors(sector_map, ticker_to_series_id)
    active_ids = [s["lead"] for s in active_nonshadow(
        fold(deps.registry.events_for_lead(lead))
        for lead in deps.registry.all_leads() if lead != SYSTEM_LEAD)]
    return lead_sectors(list(ticker_to_series_id.values()), s2sec, active_ids)


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
            target = resolve_soi_target(int(entry.cik), deps.edgar_client)
            if target is None:
                continue  # NOT-YET: SOI unindexed / ambiguous exhibit -> stays sectors_unresolved
            soi_sensor.scan(
                launch, target.accession, entry.name, active, soi, deps.cfg, now, store.append,
                fetch_body=lambda t=target: deps.edgar_client.filing_text(
                    t.cik, t.accession, t.primary_doc))
        except Exception as e:  # one launch's failure never blinds the others (§9g)
            _emit_fault(store, "soi.corroboration", e, now, faults)
    runlog.sensors["soi_corroboration"] = "ran"


def _materialize_snapshots(deps: RunnerDeps, store, now: str, faults: list) -> dict:
    """Run-order step 6 (§9): re-fold every real lead and materialize on the reactive cadence
    (`should_snapshot` — immediate on a state change, dense while active, weekly floor otherwise).
    Returns {lead: [changed fields]} for the push decision (§10). `_system` is infra, not a lead
    (mirrors the CLI's lead views) — its events fold into the run-log/queue, never a lead snapshot.

    The prior state for the state-change comparison is read from the lead's LAST snapshot (before
    this tick writes a new one), so `state_changed(prior, new)` is honest. A snapshot divergence is
    a SOFT fault (fault_sink=store.append), not a run-abort; one lead's failure never blinds the
    others (§9g)."""
    snap_cfg = SnapshotConfig.from_cfg(deps.cfg.get("snapshots") or {})
    now_dt = parse_ts(now)
    changed_leads: dict = {}
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
            decision = should_snapshot(new_state, last_ts, changed, now_dt, snap_cfg)
            if decision.save:
                write_snapshot(deps.layout, deps.registry, lead, new_state, decision.reason, now,
                               fault_sink=store.append)
        except Exception as e:  # one lead's failure never blinds the others (§9g)
            _emit_fault(store, "snapshot", e, now, faults, lead=lead)
    return changed_leads
