"""§10 in the runner — the nuisance-alarm suppression + the weekly heartbeat, over the REAL `run_tick`.
Offline (the conftest network guard). Reuses the production-faithful `test_runner` harness so the deps are
real (injected EDGAR/price/holdings fetches, the frozen store). The load-bearing invariants:

  - a RECURRING identical fault pages ONCE, then rides the heartbeat (the GPWS 'cried wolf' failure mode
    the build note's C.1 forbids) — NOT once per tick;
  - a NEW/CHANGED fault after a suppressed one pages again (a changed fault is never swallowed);
  - `--heartbeat` fires the weekly dead-man REGARDLESS of activity, and STILL on a faulted tick (a
    heartbeat email proves the whole pipeline ran).
"""

from prospector.ingest.edgar import EdgarError
from prospector.runner import run_tick
from prospector.runner.notify import NullNotifier
from tests.test_runner import XLK_ROW, _deps, _fetch_mf_only


def _raise_edgar(url, headers):
    # A deterministic, stable EDGAR failure -> the same `ingest.mf_tickers` fault (identical message) every
    # tick: the nuisance case. (Prices use the default OK fetch, so this is the tick's ONLY moving fault.)
    raise EdgarError("edgar is down", status=500)


def _tick(layout, registry, fetch, *, day, notifier, heartbeat=False):
    """One tick on the shared store with a distinct run_id + `now` (a later day) so the run-logs are
    distinct and `_load_prior_faults` reads the genuinely-prior run."""
    now = f"2026-07-{day:02d}T22:30:00Z"
    deps = _deps(layout, registry, fetch, now=now, notifier=notifier, run_id=f"run_{day:02d}")
    deps.heartbeat = heartbeat  # RunnerDeps is a plain dataclass — set the weekly flag per tick
    return run_tick(deps)


# === nuisance-alarm suppression (the one thing §10 owns beyond plumbing) ============================

def test_recurring_fault_pages_once_then_rides_the_heartbeat(layout, registry):
    notifier = NullNotifier()
    r1 = _tick(layout, registry, _raise_edgar, day=2, notifier=notifier)
    r2 = _tick(layout, registry, _raise_edgar, day=3, notifier=notifier)
    r3 = _tick(layout, registry, _raise_edgar, day=4, notifier=notifier)
    # The SAME fault every tick pages ONCE (day 2, new), then is suppressed (days 3-4) — not 3 pages.
    assert r1.pushed is True
    assert r2.pushed is False and r3.pushed is False
    assert len(notifier.pushes) == 1


def test_a_changed_fault_after_a_suppressed_one_pages_again(layout, registry):
    notifier = NullNotifier()
    _tick(layout, registry, _raise_edgar, day=2, notifier=notifier)   # fault A -> page
    _tick(layout, registry, _raise_edgar, day=3, notifier=notifier)   # fault A again -> suppressed

    def _raise_changed(url, headers):
        raise EdgarError("edgar timeout", status=504)                 # same subsystem, CHANGED message

    r = _tick(layout, registry, _raise_changed, day=4, notifier=notifier)
    assert r.pushed is True                     # a changed fault is NEVER swallowed
    assert len(notifier.pushes) == 2            # A (day 2) + changed (day 4); day 3 suppressed


# === the weekly heartbeat / dead-man ================================================================

def test_heartbeat_fires_regardless_of_activity(layout, registry):
    # A QUIET tick (no state change, no fault) with --heartbeat: no push, but the dead-man still fires.
    notifier = NullNotifier()
    r = _tick(layout, registry, _fetch_mf_only([XLK_ROW]), day=2, notifier=notifier, heartbeat=True)
    assert r.pushed is False and len(notifier.pushes) == 0
    assert len(notifier.heartbeats) == 1        # fires regardless of activity (the dead-man)


def test_heartbeat_still_fires_on_a_faulted_tick(layout, registry):
    # Even when the tick faults, the heartbeat still sends (silence must never mean 'ran but broken').
    notifier = NullNotifier()
    r = _tick(layout, registry, _raise_edgar, day=2, notifier=notifier, heartbeat=True)
    assert r.pushed is True and len(notifier.pushes) == 1   # the new fault pages ...
    assert len(notifier.heartbeats) == 1                    # ... AND the heartbeat rides along


def test_a_quiet_daily_tick_without_heartbeat_sends_nothing(layout, registry):
    # The anti-slot-machine cadence: a quiet daily tick pushes nothing and — with a heartbeat already sent
    # within the cadence (M7-01) — sends no heartbeat either (a catch-up fires only when one is overdue).
    from prospector.runner.runner import record_heartbeat_sent
    from prospector.store.event_store import EventStore
    record_heartbeat_sent(EventStore(layout, registry), "2026-06-30T22:30:00Z")  # 2d before the day-2 tick
    notifier = NullNotifier()
    r = _tick(layout, registry, _fetch_mf_only([XLK_ROW]), day=2, notifier=notifier)
    assert r.pushed is False
    assert notifier.pushes == [] and notifier.heartbeats == []
