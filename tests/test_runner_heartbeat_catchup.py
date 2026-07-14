"""M7-01 — the weekly dead-man CATCHES UP a missed heartbeat (cold-read QA, 2026-07-14; LANDED).

Finding. `ops/run.sh` decided heartbeat day by wall-clock (`date +%u -eq 7`, local Sunday) at the instant
it executed. launchd coalesces a `StartCalendarInterval` fire missed while the Mac slept into a single
catch-up run ON WAKE — which ran `pros run` WITHOUT `--heartbeat`, so a Mini asleep across the Sunday fire
never sent that week's heartbeat. Because a MISSING weekly heartbeat is the project's "the runner is dead"
signal, a benign sleep-across-Sunday produced a FALSE dead-man (the GPWS §2.4 cry-wolf trap).

Fix (M7-01). The runner owns the cadence. "Last heartbeat sent" is a folded `heartbeat.sent` event on the
`_system` stream (not a sidecar); `runner.heartbeat_is_due(registry, now, cfg)` is a UTC gap-check over it
(>= `schedule.heartbeat_cadence_days`, DEFAULT 7), so a tick the Mac slept through catches ONE heartbeat up
on wake — retiring run.sh's local-weekday gate and `weekly_day` (M7-05). `record_heartbeat_sent` writes the
fact, and only on a clean send (the run_tick failed-send test in test_runner.py pins that). This test pins
the due-gate contract.
"""

from prospector.runner.runner import heartbeat_is_due, record_heartbeat_sent
from prospector.store.event_store import EventStore

CFG = {"schedule": {"daily_utc": "22:30", "heartbeat_cadence_days": 7}}
TICK = "2026-07-13T22:30:00Z"


def test_heartbeat_is_due_catches_up_a_missed_cycle(layout, registry):
    # NEVER sent -> due (the first tick confirms the channel — the dead-man is never silently unconfirmed).
    assert heartbeat_is_due(registry, TICK, CFG) is True

    store = EventStore(layout, registry, clock=lambda: TICK)
    record_heartbeat_sent(store, "2026-07-05T22:30:00Z")   # 8 days before the tick — a cycle was missed
    assert heartbeat_is_due(registry, TICK, CFG) is True, (
        "an 8-day-stale heartbeat on a non-heartbeat-day tick was not flagged due — a missed cycle is "
        "never caught up, so the dead-man goes silent for a live week")

    record_heartbeat_sent(store, "2026-07-12T22:30:00Z")   # 1 day ago (newest wins over the 8d-old one)
    assert heartbeat_is_due(registry, TICK, CFG) is False, (
        "a heartbeat sent yesterday should not trigger a catch-up today (no double-paging)")


def test_heartbeat_cadence_defaults_to_seven_when_unconfigured(layout, registry):
    store = EventStore(layout, registry, clock=lambda: TICK)
    record_heartbeat_sent(store, "2026-07-05T22:30:00Z")   # 8 days ago
    assert heartbeat_is_due(registry, TICK, {"schedule": {}}) is True   # missing cadence key -> default 7
    assert heartbeat_is_due(registry, TICK, {}) is True                 # missing schedule entirely -> 7
