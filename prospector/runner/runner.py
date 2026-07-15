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
§9a mf-tickers + sector-prices ingest, §4a xcorr (the PRIMARY live lead-spawner), §4b dispersion
(§9e shadow), §4c launch-recording, the §9d deferred SOI-corroboration retry, the §4d mandate-diff
(§9c frozen-prior), the §4d rebalance holdings-diff accretion (the LAST M4 sensor into the runner —
reuses the §9e holdings vertical), and §10 the email sender (heartbeat/state-change/fault push,
nuisance-suppressed). The runner's sensor phase is now WHOLE — no remaining spec-cited sensor SLOTs.

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
from prospector.dashboard import views
from prospector.fold.fold import active_nonshadow, fold, state_changed
from prospector.fold.snapshots import SnapshotConfig, should_snapshot, write_snapshot
from prospector.identity.resolution import ResolutionMachine
from prospector.ingest.edgar import (SOI_AMBIGUOUS, SOI_ERROR, classify_soi_target,
                                     latest_prospectus, prospectus_history)
from prospector.ingest import capture
from prospector.ingest.holdings import (MembershipSnapshot, priceable_members, priced_coverage,
                                         weight_covering_members)
from prospector.ingest.prices import (CALENDAR_PER_TRADING_DAY, PriceIngestError, build_panel,
                                       guard_live_source, required_pull_start)
from prospector.ingest.prospectus import ProspectusIngest
from prospector.ingest.soi import SoiIngest
from prospector.runner import email_render
from prospector.runner.deps import RunnerDeps
from prospector.runner.runlog import RunLog, recent_runs, write_run_log
from prospector.sensors import dispersion as dispersion_sensor
from prospector.sensors import launch as launch_sensor
from prospector.sensors import mandate as mandate_sensor
from prospector.sensors import rebalance as rebalance_sensor
from prospector.sensors import soi as soi_sensor
from prospector.sensors import xcorr as xcorr_sensor
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.launch_corroboration import (lead_sectors, pending_soi_resolution,
                                                     series_id_sectors)
from prospector.sensors.rebalance import (active_incl_shadow_lead_ids,  # §4d rebalance active set
                                          active_nonshadow_lead_ids,  # §6 capture: shadow never captures
                                          watching_leads)  # §10: on_live_lead routing for advisories
from prospector.store.backup import last_backup_ts  # M7-02: fold backup health into the ONE fault channel
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


def _emit_fault(store, subsystem: str, message, now: str, faults: list, *, lead: str | None = None,
                key: str | None = None, category: str = "operational", series_id: str | None = None,
                on_live_lead: bool = False, extra: dict | None = None):
    """A SOFT fault (§9g): a per-unit failure is recorded on `_system` and the tick continues —
    one fund's 404 or one basket's degenerate matrix must not blind the others. Never raises: the
    fault surface itself must not abort the run (a fault while recording a fault is swallowed, so
    the dead-man push still fires). THE single fault-emit path (§10 taxonomy): the runner's soft-faults
    call it directly; a sensor's extraction-unreliable advisory reaches it through the runner-provided
    fault-reporter callback (see `_advisory_reporter`) — so every fault lands in the ONE `faults`
    accumulator (that split — sensors writing `emit({"type":"fault"})` straight to the store, bypassing
    this list — is exactly the bug that showed '0 faults this run' beside nine that fired).

    §10 CATEGORY (the alarm-posture taxonomy, CONTRACT): `operational` (something broke — a failed fetch,
    a tripped guard, a degenerate matrix; it PAGES) vs `review-advisory` (a sensor correctly PUNTED an
    unreliable extraction to a human — nothing broke; counted + surfaced but does NOT page, UNLESS its
    fund touches a live lead → `on_live_lead=True`). `_compute_push` reads exactly this. Runner soft-faults
    default `operational`; a sensor advisory passes `category="review-advisory"` + its `series_id` (+ the
    reporter's computed `on_live_lead`).

    §10 CONVENTION — **if a fault message can carry a per-tick token (a URL, timestamp, reset-epoch,
    row count), pass a STABLE `key=`.** `key` is the nuisance-suppression comparand — the identity of
    "the same failure" across ticks — held SEPARATELY from the human-readable `message` so the fossil
    keeps the full detail for forensics while suppression keys on the stable part. Default None keeps
    keying on the message (correct for the many faults whose message is already stable). This exists
    because a message-exact signature over a moving message reads a *persisting* failure as NEW every
    tick and pages daily — the GPWS 'cried wolf' mode §10's suppression is built to prevent (the
    live Tiingo/Yahoo price URLs carry moving startDate/endDate/period epochs; see `_fault_signature`)."""
    faults.append({"subsystem": subsystem, "message": str(message), "key": key,
                   "category": category, "series_id": series_id, "on_live_lead": on_live_lead})
    payload = {"subsystem": subsystem, "message": str(message), "category": category}
    if key is not None:
        payload["key"] = key
    if series_id is not None:
        payload["series_id"] = series_id
    if on_live_lead:
        payload["on_live_lead"] = True
    if extra:
        payload.update(extra)  # sensor-provided forensics (accession, ticker) — never overrides the above
    if lead is not None:
        payload["lead"] = lead
    try:
        store.append({"ts": now, "lead": SYSTEM_LEAD, "type": "fault",
                      "payload": payload, "schema": 1})
    except Exception:  # recording a fault must never itself abort the tick
        pass


def _advisory_reporter(store, now: str, faults: list, universe_ids, active_ids):
    """Build the §10 fault-reporter a sensor uses to raise a REVIEW-ADVISORY (an extraction-unreliable
    punt to a human — the sensor working correctly, declining to guess; nothing broke). It routes the
    advisory through the ONE `_emit_fault` accumulator (never a raw `store.append({"type":"fault"})` —
    that bypass is exactly the split-path bug that showed '0 faults this run' beside nine that fired), and
    computes page-worthiness HERE, where the lead context lives: an advisory whose fund touches a live
    (active, non-shadow) lead pages (`on_live_lead`, via the shared forward-hash `watching_leads`); every
    other advisory is counted + surfaced (heartbeat/dashboard) but does NOT page. The risk-owner's call:
    a held/watched fund quietly rewording its mandate is the one advisory worth interrupting for."""
    def report(subsystem: str, message: str, series_id: str | None, extra: dict | None = None) -> None:
        on_live = bool(series_id and watching_leads(series_id, universe_ids, active_ids))
        _emit_fault(store, subsystem, message, now, faults, category="review-advisory",
                    series_id=series_id, on_live_lead=on_live, extra=extra)
    return report


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


def _fault_signature(faults: list) -> frozenset:
    """A tick's fault set as an order-insensitive `(subsystem, key-or-message)` signature — the comparand
    for the §10 nuisance-alarm suppression. Keys on the STABLE `key` when a fault carries one (an HTTP
    fault keys on `(ticker, status)`, NOT the URL-bearing message whose dates move every tick), else on
    the message (the many faults whose message is already stable). A key/message delta is a *changed*
    fault (it pages); an identical repeat is a nuisance (it does not) — the build-note line 'never swallow
    a changed fault', now robust to a persisting failure whose *message* carries a moving token (the
    volatile-message finding, docs/notes/email_nuisance_suppression_findings.md). Both dimensions of the HTTP
    key — the ticker AND the status — are load-bearing: a different failing ticker OR a changed status is
    a different fault and must page, so the key must never be coarsened to subsystem-only (tests pin both)."""
    return frozenset((f.get("subsystem"), f.get("key") or f.get("message")) for f in faults)


def _load_prior_faults(layout, registry) -> list:
    """The immediately-prior run's fault list, read from the FOSSIL RECORD — the run-log FILE (the `runs`
    table indexes only `fault_count`; the full list lives in the JSON). This is the nuisance-suppression
    comparand: 'is this tick's fault new/changed vs the last run?'. Same 'prior from the frozen record,
    never a side cache' discipline as `_load_prior_mf_snapshot`. At push time in `run_tick`'s finally THIS
    run's log is not yet written, so `recent_runs(...)[0]` is genuinely the prior run. Returns [] when there
    is no prior run (first tick ever) or the file is unreadable — so a first/again fault always pages."""
    try:
        rows = recent_runs(registry, limit=1)
        if not rows:
            return []
        path = layout.root / rows[0]["file_path"]
        return json.loads(path.read_bytes()).get("faults", []) or []
    except Exception:
        return []  # a missing/corrupt prior run-log must not blind the push — treat as 'no prior fault'


def _page_worthy_faults(faults: list) -> list:
    """The §10 fault-taxonomy filter — which faults DRIVE a page (CONTRACT, alarm posture). `operational`
    faults always (something broke — a failed fetch, a tripped guard, a degenerate matrix). `review-advisory`
    faults ONLY when their fund touches a live lead (`on_live_lead`) — a held/watched fund quietly rewording
    its mandate is the one advisory worth interrupting for; every other advisory (a new-launch fund's
    unreadable prospectus — the sensor correctly punting, nothing broken) is counted + surfaced but does NOT
    page. Non-page-worthy advisories stay in `faults` for the count/display; only the push decision filters
    them out — the shadow-push discipline one layer down (keep the record whole, filter at the decision).
    A fault with no/unknown `category` is treated as operational (it pages — the fail-safe default: an
    unrecognized fault must not silently escape the alarm). Only an explicit `review-advisory` is held back;
    this matches `email_render._page_worthy` exactly, so the count/subject and the push decision agree."""
    return [f for f in faults
            if f.get("category", "operational") != "review-advisory" or f.get("on_live_lead")]


def _compute_push(page_worthy: dict, faults: list, prior_faults: list) -> bool:
    """§10 CONTRACT — push iff a NON-SHADOW `fold.state_changed` OR a NEW/changed PAGE-WORTHY fault.

    (1) NON-SHADOW STATE CHANGE. `page_worthy` is exactly the leads non-shadow *after* a
    {status,shadow,verdict} change (see `_materialize_snapshots`). §9e resolved a two-CONTRACT collision:
    §8a says push on state change, §4b says a SHADOW lead is excluded from paging. A dispersion shadow
    spawn (`status: None->active`, `shadow: True`) IS a state change but must NOT page — gating on
    non-shadow-after-the-change suppresses shadow spawn/tick/revert (the fold leaves `shadow=True` on a
    revert), leaves every xcorr path unchanged, and pages a future promotion (`shadow: true->false`) free.

    (2) FAULT TAXONOMY + NUISANCE-ALARM SUPPRESSION (§10). Only PAGE-WORTHY faults drive a push
    (`_page_worthy_faults` — operational faults + review-advisories on a live-lead fund); a review-advisory
    on a non-live-lead fund is counted + surfaced but never pages (the alarm-posture CONTRACT — a sensor
    correctly punting an unreadable extraction to a human is not 'look now'). Among the page-worthy set, the
    naive 'any fault every tick' paged on EVERY recurrence — the GPWS 'cried wolf' failure the sender slice
    exists to prevent. Instead: push once on a NEW or CHANGED page-worthy fault (signature differs from the
    immediately-prior run's PAGE-WORTHY subset), then fall to the weekly heartbeat while the SAME fault
    persists. A *cleared* fault does not push. The runlog's `faults` still record ALL of it (the fossil stays
    whole); only the push decision filters. Ticks, silent corroborations, queue mechanics, and non-live-lead
    advisories produce no page-worthy delta, so they never push — the anti-slot-machine cadence."""
    if page_worthy:
        return True
    pw = _page_worthy_faults(faults)
    if not pw:
        return False  # quiet, or only non-live-lead advisories — they ride the next heartbeat, never a push
    return _fault_signature(pw) != _fault_signature(_page_worthy_faults(prior_faults))


def _email_context(deps, store, now: str, date: str, runlog: RunLog, changed_leads: dict,
                   faults: list, pushed: bool) -> dict:
    """Gather the §8a email folds ONCE — a bounded read of the record THIS tick just wrote (the same
    `views.*` view-models the dashboard/board-snapshot render, so the email cannot drift from the screen).
    Synthesizes THIS run as the newest run row so the heartbeat's dead-man reflects the tick that is
    *sending* it (this run-log is not written until after the push). A read-only ResolutionMachine serves
    the manual queue (None if it cannot be opened -> an empty queue, never a crash)."""
    states = views.fold_all_leads(deps.registry)
    this_run = {"ts": now, "date": date, "run_id": deps.run_id, "pushed": pushed,
                "fault_count": len(faults), "config_hash": runlog.config_hash}
    runs = [this_run, *recent_runs(deps.registry)]
    try:
        machine = ResolutionMachine(deps.registry, store, None, None)
    except Exception:
        machine = None  # the queue degrades to empty; a missing resolution_queue never blanks the email
    return email_render.build_context(deps.registry, states, runs, machine, deps.cfg, now,
                                      faults=faults, changed_leads=changed_leads, trigger="run")


def heartbeat_is_due(registry, now: str, cfg: dict) -> bool:
    """§10 dead-man cadence gate (M7-01). A heartbeat is DUE when the record shows none sent within the
    cadence — read from the folded `heartbeat.sent` stream on `_system` (the ONE clock the sender writes
    and the dead-man reads). NEVER-sent -> due (the first tick confirms the channel); an unparseable prior
    ts -> due (fail toward SENDING — never silently skip the one health channel). Cadence is
    `schedule.heartbeat_cadence_days` (DEFAULT 7). A UTC gap-check owned by the runner: a tick the Mac
    slept through catches up on wake, retiring run.sh's local-weekday gate + `weekly_day` (M7-05)."""
    rows = registry.events_by_type("heartbeat.sent")
    if not rows:
        return True
    cadence = int((cfg.get("schedule") or {}).get("heartbeat_cadence_days", 7))
    try:
        return (parse_ts(now) - parse_ts(rows[-1]["ts"])).days >= cadence
    except Exception:
        return True  # an unparseable last-sent must not silence the dead-man


def record_heartbeat_sent(store, ts: str, *, trigger: str = "cadence") -> None:
    """Fossilize a `heartbeat.sent` on `_system` at `ts` (M7-01) — the append-only record of 'the dead-man
    spoke'. CRITICAL: emit this ONLY after a clean notifier hand-off (never on attempt) — a failed send
    must not advance the clock, or the dead-man goes quiet believing it spoke. `trigger` is 'cadence' (the
    runner's due-check) or 'manual' (a `--heartbeat` force-send). This is the ONE fact both the send gate
    (`heartbeat_is_due`) and the §8a liveness (`views.heartbeat`) read — one clock, two consumers."""
    store.append({"ts": ts, "lead": SYSTEM_LEAD, "type": "heartbeat.sent",
                  "payload": {"trigger": trigger}, "schema": 1})


def _check_backup_freshness(deps: RunnerDeps, store, now: str, faults: list) -> None:
    """M7-02: fold a `backup.stale` fault for any configured backup target lacking a FRESH last-success
    marker — the ONE backup-health channel (decision docs/decisions/2026-07-14-backup-health-one-fault-
    channel.md). `pros backup` stamps a marker on each target on VERIFIED success; the runner reads it here
    and emits an operational fault the §8a heartbeat already carries, so a failing backup reaches the
    operator's one health channel instead of dying in the launchd stderr log. Read-only: reads a marker off
    the external drive, writes nothing to it (the firewall + read-only posture hold).

    Two triggers into one fault (§decision-2): a MISSING marker (never-backed-up, unmounted, or lost) and a
    STALE marker (older than `backup.max_age_days`, DEFAULT 3) are the same actionable fact — no fresh
    backup, go look — so both emit `backup.stale`. The threshold is a small multiple of the daily tick
    (the runner reads the PRIOR tick's backup) so a slept-through cycle doesn't cry wolf; a genuinely-behind
    drive faults within a couple ticks. Stable per-target `key=` (message carries the moving ts/now for
    forensics) → a persisting-stale drive pages once then rides the heartbeat (the §10 E1/R4 convention). No
    configured targets → nothing to check (a dev box's empty targets faults loudly at `pros backup` time)."""
    bcfg = deps.cfg.get("backup") or {}
    targets = bcfg.get("targets") or []
    if not targets:
        return
    max_age = int(bcfg.get("max_age_days", 3))
    for t in targets:
        ts = last_backup_ts(t)
        if ts is None:
            _emit_fault(store, "backup.stale",
                        f"no successful-backup marker on {t} — the fossil record has no confirmed backup on "
                        "this drive (never backed up, unmounted, or the marker was lost); check the drive "
                        "and run `pros backup`", now, faults, key=f"backup.stale:{t}")
            continue
        try:
            stale = (parse_ts(now) - parse_ts(ts)).days >= max_age
        except Exception:
            stale = True  # an unparseable marker cannot attest freshness — fault toward loud (§8 fail-loud)
        if stale:
            _emit_fault(store, "backup.stale",
                        f"newest successful backup on {t} is {ts}, over {max_age}d stale as of {now} — the "
                        "fossil record is not being backed up; check the drive and run `pros backup`", now,
                        faults, key=f"backup.stale:{t}")


def run_tick(deps: RunnerDeps) -> RunLog:
    """Execute ONE cadence tick in the CONTRACT run order (§9):

        1. config honesty (fossilize a config change BEFORE any sensor)   [subtle bit #1]
        2. ingest            (§9a — mf-tickers + the sector-price panel)
        3. sensors §4a-§4d   (WIRED: xcorr §4a, dispersion §4b/§9e shadow, launch §4c, mandate §4d, SOI §9d)
        4. identity retries  (drain the retry-then-manual queue)
        5. capture           (§6 discourse capture — WIRED at M6; disabled until armed)
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

        # M7-02: assess backup health (the ONE channel — a stale/missing last-success marker on a configured
        # target folds a `backup.stale` fault the §8a heartbeat carries). In the `finally` alongside snapshots
        # so it reports even on a faulted/crashed tick, and BEFORE `_compute_push` so its fault feeds the push
        # comparand and the heartbeat count — a backup that isn't happening is exactly a weekly-email fact.
        try:
            _check_backup_freshness(deps, store, now, faults)
        except Exception as e:  # the freshness read must never abort the run-log write
            _emit_fault(store, "backup.check", e, now, faults)

        # §10 NUISANCE-ALARM SUPPRESSION: compare this tick's faults to the prior run's (from the fossil,
        # before THIS run-log is written), so a recurring identical fault rides the heartbeat, not a page.
        prior_faults = _load_prior_faults(deps.layout, deps.registry)
        pushed = _compute_push(page_worthy, faults, prior_faults)  # NON-shadow change OR new/changed fault

        # §10 SENDER: build the §8a email folds ONCE, then dispatch. A state-change/fault push AND the
        # weekly heartbeat can BOTH fire this tick (a change on a weekly run). The notifier RAISES on a
        # send failure — caught here as a soft `notify` fault so a broken sender never loses the run-log
        # (a fault email beats silence; the dead-man still records). NullNotifier just records the context.
        # §10 heartbeat cadence (M7-01): the RUNNER decides heartbeat day now — a UTC gap-check on the
        # folded `heartbeat.sent` — so a tick the Mac slept through catches one up on wake (the old
        # run.sh local-weekday gate silently dropped a sleep-across-Sunday heartbeat). `--heartbeat`
        # (`deps.heartbeat`) still force-sends manually.
        send_heartbeat = deps.heartbeat or heartbeat_is_due(deps.registry, now, deps.cfg)
        if pushed or send_heartbeat:
            try:
                ctx = _email_context(deps, store, now, date, runlog, changed_leads, faults, pushed)
            except Exception as e:  # a fold/context failure must not abort the run-log write
                ctx = None
                _emit_fault(store, "notify.context", e, now, faults)
            if ctx is not None:
                if pushed:
                    try:
                        deps.notifier.push(ctx)
                    except Exception as e:  # a send failure is a soft fault — it must not lose the run-log
                        _emit_fault(store, "notify", e, now, faults)
                if send_heartbeat:  # the weekly dead-man — fires on cadence (or --heartbeat), catches a gap up
                    try:
                        deps.notifier.heartbeat(ctx)
                        # M7-01 CRITICAL: record the send ONLY after a CLEAN hand-off (inside the try), so a
                        # raising send skips the record and the clock does NOT advance — the dead-man must
                        # never fall silent believing it spoke. Through `store` so §9g counts it.
                        record_heartbeat_sent(store, now,
                                              trigger="manual" if deps.heartbeat else "cadence")
                    except Exception as e:
                        _emit_fault(store, "notify.heartbeat", e, now, faults)

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
    the §4d mandate-diff accretion, the §4d rebalance holdings-diff accretion (reusing the §9e vertical),
    and the §9d SOI-corroboration deferred pass. The CONTRACT run order stays visible in code (a test
    pins it). One ResolutionMachine (with a real FundRegistry) serves both launch and the retries, so a
    retry that resolves can complete its registry entry.

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
    #    §4d rebalance — WIRED (the holdings-diff ACCRETION sibling of mandate; the LAST M4 sensor into
    #        the runner). Reuses the §9e holdings vertical: diffs each basket's frozen holdings today vs
    #        the most-recent prior, accreting a `rebalance` onto the live leads it touches (INCLUDING
    #        shadow — accretion never pages). First sight seeds silently; a broken feed faults the basket.
    try:
        _run_rebalance(deps, store, now, faults, runlog, current_mf)
    except Exception as e:  # a batch-level failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["rebalance"] = "fault"
        _emit_fault(store, "sensor.rebalance", e, now, faults)

    # 4. IDENTITY RETRIES (§9-run-order-4). Drain the retry-then-manual queue; nothing evaporates.
    try:
        machine.run_retries()
        runlog.sensors["identity_retries"] = "ran"
    except Exception as e:  # a retry-pass failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["identity_retries"] = "fault"
        _emit_fault(store, "identity.retries", e, now, faults)

    # 5. CAPTURE (§9-run-order-5, §6) — WIRED (M6, the last v1 build slice). Deterministic-templated
    #    discourse capture over the tick's ACTIVE NON-SHADOW leads (shadow burn-in is not trusted enough
    #    to spend on), AFTER the sensor phase (captures reference the tick's leads) and before the
    #    wrapper's backup step (so the night's captures reach the HDDs same-night). DISABLED unless armed
    #    (capture.monthly_budget_usd set + ANTHROPIC_API_KEY present); a HARD budget cap pauses + faults
    #    on breach (never a silent overrun). Nothing in v1 READS a capture — a write-only substrate for
    #    v2 (CLAUDE.md wall, enforced by the never-read-wall test).
    try:
        _run_capture(deps, store, now, faults, runlog)
    except Exception as e:  # a capture-phase failure is a soft fault, never a run-abort (§9g)
        runlog.sensors["capture"] = "fault"
        _emit_fault(store, "capture", e, now, faults)


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
            # §10: the message keeps the URL (moving startDate/endDate) for forensics, but the SUPPRESSION
            # key is (ticker, status) — a persisting lapsed-sub 403 is ONE fault, not a new one each tick,
            # so it pages once then rides the heartbeat (`status` is set on Price/EdgarError HTTP failures).
            _emit_fault(store, "ingest.prices", f"{t}: {e}", now, faults,
                        key=f"{t}:{getattr(e, 'status', None)}")
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
            # §10: same discipline as the sector-panel pull — a persisting per-basket HTTP failure keys on
            # (ticker, status), not the URL-bearing message, so it pages once then rides the heartbeat.
            _emit_fault(store, "sensor.dispersion", f"{ticker}: {e}", now, faults, lead=lead_id,
                        key=f"{ticker}:{getattr(e, 'status', None)}")
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
    report_advisory = _advisory_reporter(store, now, faults, universe_ids, active_ids)  # §10 taxonomy
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
                                universe_ids, active_ids, prospectus, mandate_cfg, now, store.append,
                                report_advisory)
        except Exception as e:  # one fund's failure never blinds the others (§9g)
            _emit_fault(store, "mandate", e, now, faults)
    runlog.sensors["mandate"] = "ran"


def _run_rebalance(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog,
                   current_mf: dict | None) -> None:
    """§4d rebalance — holdings-diff ACCRETION, the LAST M4 sensor into the runner. For each resolvable
    SPDR basket THIS tick, diff its frozen holdings today vs the most-recent prior frozen pull and, on a
    MATERIAL change (an identified-security add/drop, or a weight move >= `rebalance.weight_delta_
    threshold`), accrete a `rebalance` onto every live lead whose baskets include the fund (forward-hash
    routing, CONTRACT §4d), else onto `_system` (kept, not surfaced). Accretion only: it NEVER spawns,
    never pages (the fold folds `rebalance` as a silent corroboration).

    ACTIVE SET — INCLUDING SHADOW (`active_incl_shadow_lead_ids`, not the non-shadow paging helper).
    Rebalance accretes and never pages, so unlike the mandate/SOI paging paths it SHOULD corroborate
    shadow (burn-in) dispersion leads — right now every dispersion lead is shadow, so the non-shadow
    filter would sever rebalance from the whole dispersion side. Safe by construction (see the sensor
    helper's docstring). The set is read from the MATERIALIZED fold (CONTRACT §4d) — a lead spawned THIS
    tick is not yet snapshotted (step 6), so a basket that both spawns and rebalances on one tick routes
    that first rebalance to `_system` and accretes from the next tick on (self-correcting; the record
    still holds it). That one-tick lag on a rare co-occurrence is the CONTRACT's trade — re-folding here
    to erase it is the drift-risk §4d forbids. Ratified: docs/decisions/2026-07-12-rebalance-runner-wiring.md.

    CURRENT holdings come from today's FROZEN file (the §9e dispersion pass froze it earlier this tick),
    with PULL-IF-ABSENT so rebalance is self-sufficient (never silently depends on dispersion having run).
    Fault/seed boundary (build note, corrected):
      - a broken/unparseable CURRENT feed -> a per-basket OPERATIONAL fault (§9g), continue (a real break
        must surface — the fault path the seed case must not swallow);
      - NO prior frozen pull (first sight) -> SEED SILENTLY: no event, no fault. A cold start is the
        expected initial state of an append-only record, not a malfunction — the same first-sight
        baseline launch (seeds) and mandate (baselines) already do; diffing begins next tick.
    Idempotency (mirrors the N-series discipline): a re-run of THIS tick does not double-emit — a basket
    whose (series_id, as_of=today) `rebalance` is already in the record is skipped.

    `runlog.sensors['rebalance']` is 'ran' (>=1 basket drove the diff), 'seeded' (only first-sight
    baselines this tick), or 'skipped' (no resolvable basket) — never a silent no-op."""
    ticker_to_series_id = _universe_series_ids(deps.cfg, current_mf)
    if not ticker_to_series_id:
        runlog.sensors["rebalance"] = "skipped"  # no resolvable baskets this tick — honest
        return
    universe_ids = list(ticker_to_series_id.values())
    active_ids = active_incl_shadow_lead_ids(deps.registry, deps.layout)  # INCL shadow (never pages)
    date_ = now[:10]
    source = "spdr"  # holdings ingest is SPDR-only (§4d keystone) — not the price-config'd source
    # Same-tick idempotency: the (series_id, as_of) pairs already fossilized as `rebalance`, from the
    # record (§9f — the same single-source enumeration the SOI pass uses; payload is canonical-JSON text).
    emitted = {(p.get("series_id"), p.get("as_of"))
               for lead in deps.registry.all_leads()
               for r in deps.registry.events_for_lead(lead, "rebalance")
               for p in (json.loads(r["payload"]),)}
    scanned = seeded = False
    for ticker, series_id in ticker_to_series_id.items():
        if (series_id, date_) in emitted:
            continue  # this basket's rebalance for today is already recorded — idempotent re-run
        try:
            # CURRENT = today's frozen holdings (the §9e pass froze it); pull-if-absent to stay
            # self-sufficient. A broken/unparseable feed FAULTS this basket — never seeded away.
            if deps.holdings_ingest.frozen_path(series_id, date_, ticker, source).exists():
                current = deps.holdings_ingest.load_frozen(series_id, date_, ticker, source)
            else:
                current = deps.holdings_ingest.pull(series_id, ticker, source)  # freeze-before-parse (§3)
        except Exception as e:  # broken/unparseable CURRENT feed -> per-basket OPERATIONAL fault (§9g)
            # §10: message keeps detail; the suppression key is (ticker, status) so a persisting feed
            # failure pages once then rides the heartbeat (mirrors the sector-panel / dispersion pulls).
            _emit_fault(store, "sensor.rebalance", f"{ticker}: {e}", now, faults,
                        key=f"{ticker}:{getattr(e, 'status', None)}")
            continue
        # PRIOR = the most-recent frozen date strictly before today. NONE -> SEED SILENTLY (first sight):
        # a cold start is not a fault (build-note correction — reserve faults for a broken feed).
        prior_dates = [d for d in deps.holdings_ingest.frozen_dates(series_id, source) if d < date_]
        if not prior_dates:
            seeded = True  # baselined this tick; nothing to diff yet — no event, no fault
            continue
        try:
            prior = deps.holdings_ingest.load_frozen(series_id, prior_dates[-1], ticker, source)
        except Exception as e:  # a prior we HAVE but cannot parse is genuinely broken -> fault, not seed
            # §10: the message keeps the moving prior date for forensics, but the suppression key is
            # the STABLE (ticker, status) — a persisting unparseable prior pages once then rides the
            # heartbeat (mirrors the current-feed fault 11 lines above; without key= the moving date
            # made _fault_signature differ every tick and paged daily).
            _emit_fault(store, "sensor.rebalance", f"{ticker} prior {prior_dates[-1]}: {e}", now, faults,
                        key=f"{ticker}:prior:{getattr(e, 'status', None)}")
            continue
        rebalance_sensor.scan(series_id, ticker, prior, current, universe_ids, active_ids,
                              deps.cfg, now, store.append, as_of=date_)
        scanned = True
    runlog.sensors["rebalance"] = "ran" if scanned else ("seeded" if seeded else "skipped")


def _run_capture(deps: RunnerDeps, store, now: str, faults: list, runlog: RunLog) -> None:
    """§6 discourse capture (M6). For each ACTIVE NON-SHADOW lead due for capture (never captured, or its
    last capture is >= 7 days old — the per-lead weekly gate), build K deterministic templated queries
    from lead metadata and, per query, run one web_search, fetch the top-M result URLs, and freeze ONLY
    the raw result blocks + fetched text (the wall — CLAUDE.md "No LLM text as data"). One `capture.stored`
    event per lead per capture.

    DISABLED unless armed: runs only when `capture.monthly_budget_usd` is set AND a provider is injected
    (`ANTHROPIC_API_KEY` present) — otherwise records 'disabled' and does nothing (ships off; the owner
    arms it). BUDGET is a HARD cap read FRESH each tick (the value is a tunable DEFAULT, not cached):
    before each search, if the persisted weekly search count >= `max_searches_per_week` OR the month's
    estimated spend (count x `unit_price_usd`) >= `monthly_budget_usd`, capture PAUSES and emits ONE
    operational fault with a stable key (`capture.budget:searches`/`:usd`) — pages once, then rides the
    heartbeat while the pause persists (§10, never a silent overrun/skip). A transient per-URL fetch
    failure is a soft operational fault (`capture.fetch:{status}`); the partial capture is still stored,
    never killed over one URL (§3c). Determinism (§6, no LLM authorship): the query set is OUR templating;
    if the provider issues a query different from ours, a `capture.query_drift` fault fires loud."""
    cap = deps.cfg.get("capture") or {}
    budget_usd = cap.get("monthly_budget_usd")
    if budget_usd is None or deps.capture_provider is None:
        runlog.sensors["capture"] = "disabled"  # ships off; owner arms via budget + key (build note §4)
        return
    budget = capture.CaptureBudget(deps.registry)
    max_week = int(cap.get("max_searches_per_week", 60))
    unit_price = float(cap.get("unit_price_usd") or 0.0)
    k = int(cap.get("k_queries", 5))
    m = int(cap.get("m_fetch_urls", 2))
    top_n = int(cap.get("top_n", 5))
    week_key, month_key = capture.period_keys(now)
    ran = paused = False
    for lead in sorted(active_nonshadow_lead_ids(deps.registry, deps.layout)):  # shadow never captures
        state = fold(deps.registry.events_for_lead(lead))
        if not _capture_due(state, now):
            continue
        queries = capture.build_queries(_capture_meta(deps.registry, lead, state, top_n), k, top_n)
        if not queries:
            continue  # no templatable metadata yet — nothing honest to search for
        result_counts: list = []
        wrote = False
        for n, query in enumerate(queries):
            # BUDGET (hard cap, read fresh): pause BEFORE issuing a search that would breach either cap.
            if budget.count("week", week_key) >= max_week:
                _emit_fault(store, "capture.budget",
                            f"weekly search cap reached ({max_week}) — capture paused", now, faults,
                            key="capture.budget:searches")
                paused = True
                break
            mo = budget.count("month", month_key)
            if unit_price and mo * unit_price >= float(budget_usd):
                _emit_fault(store, "capture.budget",
                            f"monthly budget reached (~${mo * unit_price:.2f} >= ${float(budget_usd):.2f}) "
                            "— capture paused", now, faults, key="capture.budget:usd")
                paused = True
                break
            try:
                res = deps.capture_provider.search(query)
            except Exception as e:  # a search failure is a soft fault; try the next query
                _emit_fault(store, "capture.search", f"{query!r}: {e}", now, faults, lead=lead,
                            key=f"capture.search:{getattr(e, 'status', None)}")
                continue
            budget.record_search(week_key, month_key, now)  # metered the moment a search is issued
            issued = res.get("query_issued")
            if issued is not None and issued != query:  # §6 no-LLM-authorship: fault loud on divergence
                _emit_fault(store, "capture.query_drift",
                            f"provider issued {issued!r} != templated {query!r}", now, faults,
                            lead=lead, key="capture.query_drift")
            blocks = res.get("result_blocks") or []
            fetched: list = []
            for url in capture.top_urls(blocks, m):  # OUR deterministic top-M URL selection
                try:
                    fetched.append({"url": url, "status": 200,
                                    "text": deps.capture_provider.fetch_page(url)})
                except Exception as e:  # store the partial; never kill the capture over one URL (§3c)
                    _emit_fault(store, "capture.fetch", f"{url}: {e}", now, faults, lead=lead,
                                key=f"capture.fetch:{getattr(e, 'status', None)}")
                    fetched.append({"url": url, "status": getattr(e, "status", None), "error": str(e)})
            capture.write_query_blob(deps.layout, lead, now, n, {
                "query": query, "query_issued": issued, "provider": capture.PROVIDER, "ts": now,
                "result_blocks": blocks, "fetched": fetched})  # ONLY result blocks + fetched text (wall)
            result_counts.append({"query_n": n, "results": len(blocks),
                                  "fetched": sum(1 for f in fetched if "text" in f)})
            wrote = True
        if wrote:
            # One capture.stored onto the lead per capture (§6). The fold reads query_set / s3_prefix /
            # result_counts into capture_inventory (the weekly gate + the dashboard count line).
            store.append({"ts": now, "lead": lead, "type": "capture.stored",
                          "payload": {"query_set": queries,
                                      "s3_prefix": capture.capture_prefix(lead, now),
                                      "result_counts": result_counts}, "schema": 1})
            ran = True
        if paused:
            break
    runlog.sensors["capture"] = "paused" if paused else ("ran" if ran else "skipped")


def _capture_due(state: dict, now: str) -> bool:
    """The per-lead weekly capture gate (§6): due if the lead has NEVER been captured (covers a lead that
    just entered active — its archive starts at landing, build note §3e) OR its most-recent capture is
    >= 7 days old. Read from the fold's `capture_inventory` (the fossil record, §9f — no side state)."""
    stamps = [e.get("ts") for e in (state.get("capture_inventory") or []) if e.get("ts")]
    if not stamps:
        return True
    return (parse_ts(now) - parse_ts(max(stamps))).days >= 7


def _capture_meta(registry, lead: str, state: dict, top_n: int) -> dict:
    """Lead metadata for deterministic query construction (§6): the basket display name (off the fold),
    top-N constituent names (from the most-recent `dispersion.tick` payload — the generous §4b payload
    carries full constituent membership, weight-desc), and concentration industries (a `sectors` list on a
    `launch` corroboration payload, when present). Read from the record (§9f); best-effort — thin metadata
    yields fewer queries, never a crash. This reads EVENT payloads, never a capture blob (the wall holds)."""
    constituents: list = []
    disp = registry.events_for_lead(lead, "dispersion.tick")
    if disp:
        payload = json.loads(disp[-1]["payload"])  # newest tick (rows ordered by ts, event_id)
        named = [(mm.get("name"), mm.get("weight") or 0.0)
                 for c in payload.get("clusters", []) for mm in c.get("members", []) if mm.get("name")]
        named.sort(key=lambda nw: (-nw[1], nw[0]))
        for name, _w in named:
            if name not in constituents:
                constituents.append(name)
    industries: list = []
    for r in registry.events_for_lead(lead, "launch"):
        for s in (json.loads(r["payload"]).get("sectors") or []):
            if s not in industries:
                industries.append(s)
    return {"display": state.get("display"), "constituents": constituents, "industries": industries}


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
    ticker_to_series_id, active_ids = _lead_context(deps, fund_registry)  # §10: on_live_lead routing
    report_advisory = _advisory_reporter(store, now, faults, list(ticker_to_series_id.values()), active_ids)
    for launch in pending:
        try:
            entry = fund_registry.get(launch["series_id"])
            if entry is None:
                continue  # no registry entry (cik/anchor) yet -> stays pending, re-attempted
            target, reason = classify_soi_target(int(entry.cik), deps.edgar_client)
            if target is None:
                # N8: a genuine NOT-YET stays silent (re-attempt next cycle); an AMBIGUOUS exhibit or an
                # ERROR is a FAULT — the filing IS there but unresolvable, so it must surface ONCE for
                # manual review, not silently re-fetch every tick for 180 days (nor mask a real bug). This
                # is a RUNNER OPERATIONAL fault (the resolver couldn't place the filing — it pages), NOT
                # the sensor's review-advisory (that is soi.scan's extraction-unreliable punt, below).
                if reason in (SOI_AMBIGUOUS, SOI_ERROR):
                    _emit_fault(store, f"soi.corroboration.{reason}",
                                f"SOI target unresolvable ({reason}) for {launch['series_id']} "
                                f"(cik {entry.cik}) — surface for manual review",
                                now, faults, lead=launch.get("lead"))
                continue  # not-yet OR surfaced-fault: the launch stays sectors_unresolved this tick
            soi_sensor.scan(
                launch, target.accession, entry.name, active, soi, deps.cfg, now, store.append,
                report_advisory,
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
                # §10: a snapshot divergence is a data-integrity break that MUST count + page. Route the
                # sink through _emit_fault so it lands in the `faults` accumulator (which the scan-line
                # count, _compute_push, and the next tick's comparand all read) — NOT a raw store.append,
                # the split-path bug that showed "0 faults this run" beside faults that fired. _emit_fault
                # also writes the store event, so the body's fault_log is unchanged.
                def _snapshot_fault_sink(event, _lead=lead):
                    _emit_fault(store, event["payload"]["subsystem"], event["payload"]["message"],
                                now, faults, lead=_lead)
                write_snapshot(deps.layout, deps.registry, lead, new_state, decision.reason, now,
                               fault_sink=_snapshot_fault_sink)
        except Exception as e:  # one lead's failure never blinds the others (§9g)
            _emit_fault(store, "snapshot", e, now, faults, lead=lead)
    return changed_leads, page_worthy
