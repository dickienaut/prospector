"""M7-02 — backup health surfaces through the ONE fault channel the §8a heartbeat already reads.

Decision: `docs/decisions/2026-07-14-backup-health-one-fault-channel.md` (+ the heartbeat-cluster build note
Ruling 2). `pros backup` stamps a last-success marker on each target ON VERIFIED success; each daily tick the
RUNNER reads it and folds a `backup.stale` fault if the newest backup is MISSING or older than
`backup.max_age_days`. That fault flows through the machinery that already exists — the §10 accumulator,
`_compute_push`, the §8a heartbeat — so a failing backup reaches the operator's one health channel instead of
dying in the launchd stderr log.

Offline (the conftest network guard); reuses the production-faithful `test_runner` harness (real `run_tick`,
injected fetches, the frozen store). The load-bearing invariants:
  - a MISSING marker on a configured target folds `backup.stale` and PAGES (never-backed-up / unmounted is
    the same actionable fact as stale — no fresh backup, go look);
  - a STALE marker (older than `max_age_days`) folds `backup.stale`; a FRESH one folds nothing;
  - NO configured targets → nothing checked (a dev box's empty targets faults at `pros backup` time, not here);
  - a PERSISTING stale backup pages ONCE then rides the heartbeat — the §10 nuisance-suppression, keyed on the
    stable per-target `key=` (the message carries the moving ts/now for forensics).
"""

import copy

from prospector.config import load_config
from prospector.runner import run_tick
from prospector.runner.notify import NullNotifier
from prospector.store.backup import SUCCESS_MARKER
from tests.test_runner import CONFIG, XLK_ROW, _deps, _fetch_mf_only


def _cfg_with_targets(target, *, max_age=3):
    """A cfg whose backup.targets points at `target` (the shipped default is empty). Original cfg_hash is
    fine — the resulting `config.changed` is not a fault and never pages (see `_compute_push`)."""
    cfg, cfg_hash = load_config(CONFIG)
    cfg = copy.deepcopy(cfg)
    cfg["backup"] = {"targets": [str(target)], "max_age_days": max_age,
                     "marker": ".prospector-backup-target"}
    return cfg, cfg_hash


def _stamp(target, ts):
    target.mkdir(parents=True, exist_ok=True)
    (target / SUCCESS_MARKER).write_text(ts, encoding="utf-8")


def _tick(layout, registry, cfg, cfg_hash, *, day, notifier=None):
    """One quiet tick (no launch: prior == current == [XLK_ROW]) with a distinct run_id + `now` (a later
    day) so the run-logs are distinct and the §10 prior-fault comparand reads the genuinely-prior run."""
    now = f"2026-07-{day:02d}T22:30:00Z"
    deps = _deps(layout, registry, _fetch_mf_only([XLK_ROW]), now=now, cfg=cfg, cfg_hash=cfg_hash,
                 run_id=f"run_{day:02d}", notifier=notifier or NullNotifier())
    return run_tick(deps)


def _stale_faults(runlog):
    return [f for f in runlog.faults if f["subsystem"] == "backup.stale"]


# -- a missing / stale marker folds backup.stale; a fresh one does not ---------------------------------

def test_missing_marker_on_a_configured_target_folds_backup_stale(layout, registry, tmp_path):
    target = tmp_path / "hd1"
    target.mkdir()                                  # configured + present, but NEVER backed up (no marker)
    cfg, h = _cfg_with_targets(target)

    runlog = _tick(layout, registry, cfg, h, day=14)

    faults = _stale_faults(runlog)
    assert len(faults) == 1
    assert faults[0]["key"] == f"backup.stale:{target}"     # stable per-target suppression key
    assert str(target) in faults[0]["message"]              # the message names the drive (fail-loud + specific)
    assert runlog.pushed is True                            # a never-backed-up drive is a new op fault → pages


def test_a_stale_marker_folds_backup_stale(layout, registry, tmp_path):
    target = tmp_path / "hd1"
    _stamp(target, "2026-07-01T22:30:00Z")          # 13 days before the day-14 tick → well past the 3d floor
    cfg, h = _cfg_with_targets(target)

    runlog = _tick(layout, registry, cfg, h, day=14)

    faults = _stale_faults(runlog)
    assert len(faults) == 1 and "2026-07-01" in faults[0]["message"]   # the stale ts is kept for forensics
    assert runlog.pushed is True


def test_a_fresh_marker_folds_no_backup_stale(layout, registry, tmp_path):
    target = tmp_path / "hd1"
    _stamp(target, "2026-07-14T00:00:00Z")          # same day as the day-14 tick → 0d old, fresh
    cfg, h = _cfg_with_targets(target)

    runlog = _tick(layout, registry, cfg, h, day=14)

    assert _stale_faults(runlog) == []
    assert runlog.pushed is False                   # quiet tick + a fresh backup → nothing to page


def test_one_slept_through_cycle_does_not_cry_stale(layout, registry, tmp_path):
    # The runner reads the PRIOR tick's backup (backup runs after the tick), so ~1d lag is normal; the 3d
    # DEFAULT tolerates that lag PLUS a slept-through cycle. A 2-day-old marker must NOT cry stale.
    target = tmp_path / "hd1"
    _stamp(target, "2026-07-12T22:30:00Z")          # 2 days before the day-14 tick → 2d < 3d floor
    cfg, h = _cfg_with_targets(target)

    runlog = _tick(layout, registry, cfg, h, day=14)

    assert _stale_faults(runlog) == []


def test_no_configured_targets_skips_the_check(layout, registry):
    # The shipped default is backup.targets: [] — the runner checks nothing (a dev box faults loudly at
    # `pros backup` time, never here). No target, no marker, no backup.stale.
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW])))
    assert _stale_faults(runlog) == []


# -- the §10 nuisance-suppression: a persisting stale backup pages once --------------------------------

def test_persisting_stale_backup_pages_once_then_rides_the_heartbeat(layout, registry, tmp_path):
    target = tmp_path / "hd1"
    target.mkdir()                                  # missing marker, persists across both ticks
    cfg, h = _cfg_with_targets(target)
    notifier = NullNotifier()

    r1 = _tick(layout, registry, cfg, h, day=14, notifier=notifier)
    r2 = _tick(layout, registry, cfg, h, day=15, notifier=notifier)

    # the SAME backup.stale (stable per-target key) is RECORDED every tick — the fossil stays whole ...
    assert _stale_faults(r1) and _stale_faults(r2)
    # ... but pages ONCE (day 14, new) then falls silent to the heartbeat (day 15, suppressed) — not daily.
    assert r1.pushed is True and r2.pushed is False
    assert len(notifier.pushes) == 1
