"""M7-01 — the weekly dead-man must CATCH UP a missed heartbeat (cold-read QA, 2026-07-14).

Finding. `ops/run.sh` decides heartbeat day by wall-clock: `if [ "$(date +%u)" -eq 7 ]` (local Sunday)
AT THE INSTANT IT EXECUTES. launchd coalesces a StartCalendarInterval fire missed while the Mac slept
into a single catch-up run ON WAKE (documented Apple behaviour). So a Mini asleep across the Sunday fire
wakes Monday and runs `pros run` WITHOUT `--heartbeat` -> that week's heartbeat never sends. There is no
"heartbeat overdue" notion anywhere in prospector/*.py (grep-confirmed: no heartbeat-sent state in the
runlog or store), so a skipped week is never made up. Because a MISSING weekly heartbeat is the project's
defined "the runner is dead" signal, a benign sleep-across-Sunday produces a FALSE dead-man — the GPWS
§2.4 cry-wolf trap on the one channel whose job is unambiguous absence.

STATUS: DECISION-DEPENDENT (xfail strict). The fix requires a design choice the QA seat should NOT make
unilaterally: WHERE the catch-up decision lives (move it into the runner, or keep it in run.sh reading a
runner-exposed "due?" signal) and WHAT records "last heartbeat sent" (a `heartbeat.sent` event, a runlog
column, or reusing recent_runs). This test encodes only the implementation-AGNOSTIC behavioural contract
and is marked xfail(strict=True): it does not fail today's suite, and it flips to a loud XPASS the moment
a catch-up mechanism lands — the signal to remove the marker (mirrors the N9 deferred-gate pattern).

BEHAVIOURAL CONTRACT (what any correct fix must satisfy): a scheduled tick that runs on a NON-heartbeat
day, when the last heartbeat was sent more than the weekly cadence ago (i.e. a Sunday was missed), must
still send a heartbeat — a catch-up — so the operator's one health channel is never silently skipped for
a week the system was alive. Conversely, when a heartbeat was sent within the cadence, a non-heartbeat-day
tick must NOT send one (no double-paging). The test expresses this against a proposed runner surface
`heartbeat_is_due(registry, now, cfg)`; the NAME/shape is illustrative — realign it to whatever interface
the fix adopts. Until that interface exists the import fails and the test registers as xfail.
"""

import pytest

# Weekly cadence in days (schedule.weekly_day -> a 7-day floor). The contract is "> one week since the
# last heartbeat".
WEEK = 7


@pytest.mark.xfail(strict=True,
                   reason="M7-01 decision-dependent: no heartbeat-overdue/catch-up mechanism exists yet; "
                          "flips to XPASS when the fix lands (remove this marker then)")
def test_overdue_heartbeat_is_caught_up_on_a_non_heartbeat_day(layout, registry):
    # The proposed catch-up surface. Absent today -> ImportError -> xfail (expected). When the fix adds
    # it, the assertions below run and (if correct) XPASS -> strict failure -> remove the marker.
    from prospector.runner.runner import heartbeat_is_due  # noqa: F401  (interface TBD by the fix)

    from prospector.store.event_store import EventStore
    store = EventStore(layout, registry, clock=lambda: "2026-07-13T22:30:00Z")

    # Record a heartbeat sent 8 days ago (last Sunday's fire), then NO heartbeat since — the Mac slept
    # through this Sunday and only a Monday catch-up ran. `record_heartbeat_sent` is the would-be write
    # side of the same mechanism; illustrative, realign to the fix's representation.
    from prospector.runner.runner import record_heartbeat_sent
    record_heartbeat_sent(store, "2026-07-05T22:30:00Z")   # 8 days before the tick below

    cfg = {"schedule": {"daily_utc": "22:30", "weekly_day": "SUN"}}

    # A Monday tick (non-heartbeat day) with the last heartbeat 8 days stale -> a catch-up is DUE.
    assert heartbeat_is_due(registry, "2026-07-13T22:30:00Z", cfg) is True, (
        "an 8-day-stale heartbeat on a non-Sunday tick was not flagged due — a missed Sunday is never "
        "caught up, so the dead-man goes silent for a live week")

    # And with a heartbeat sent within the cadence, a non-heartbeat-day tick must NOT re-send.
    store2 = EventStore(layout, registry, clock=lambda: "2026-07-13T22:30:00Z")
    record_heartbeat_sent(store2, "2026-07-12T22:30:00Z")   # 1 day ago
    assert heartbeat_is_due(registry, "2026-07-13T22:30:00Z", cfg) is False, (
        "a heartbeat sent yesterday should not trigger a catch-up today (no double-paging)")
