"""Market-stress annotation (spec §4a, CONTRACT): a stressed departure is recorded —
event_count and stress_departures move — but it is not a state change: no activation, no
latest_z update, nothing for state_changed to push on. The same departure without the flag
activates normally."""

from __future__ import annotations

import pytest

from prospector.fold.fold import fold, state_changed


def _row(event_id, ts, type_, payload):
    return {"event_id": event_id, "ts": ts, "type": type_,
            "payload": payload, "lead": "ld_s", "schema": 1}


_SPAWN = _row("s1", "2026-07-01T00:00:00Z", "lead.spawned",
              {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False})
_TICK = _row("s2", "2026-07-08T00:00:00Z", "xcorr.tick", {"z": 2.0})
_REVERT = _row("s3", "2026-07-15T00:00:00Z", "xcorr.reverted", {"z": 0.9})


def _departure(stress, event_id="d1", ts="2026-08-01T00:00:00Z", z=9.9):
    payload = {"pair": ["S000001111", "S000002222"], "z": z}
    if stress is not ...:
        payload["market_stress"] = stress
    return _row(event_id, ts, "xcorr.departure", payload)


def test_stressed_departure_without_prior_spawn_stays_none():
    state = fold([_departure(True)])
    assert state["status"] is None
    assert state["latest_z"] is None
    assert state["stress_departures"] == 1
    assert state["event_count"] == 1  # recorded, not a state change


def test_stressed_departure_after_revert_stays_reverted():
    before = fold([_SPAWN, _TICK, _REVERT])
    after = fold([_SPAWN, _TICK, _REVERT, _departure(True)])
    assert before["status"] == "reverted"
    assert after["status"] == "reverted"
    assert after["latest_z"] == before["latest_z"] == 2.0
    assert after["stress_departures"] == 1
    assert state_changed(before, after) == []


def test_stressed_departure_while_active_changes_nothing_but_counts():
    before = fold([_SPAWN, _TICK])
    after = fold([_SPAWN, _TICK, _departure(True)])
    assert after["status"] == "active"  # from the spawn, not the stressed departure
    assert after["latest_z"] == 2.0
    assert after["stress_departures"] == 1
    assert after["event_count"] == before["event_count"] + 1
    assert state_changed(before, after) == []


def test_same_departure_without_flag_activates():
    state = fold([_departure(...)])  # no market_stress key at all
    assert state["status"] == "active"
    assert state["latest_z"] == 9.9
    assert state["stress_departures"] == 0


def test_departure_after_stress_clears_fires_normally():
    rows = [_SPAWN, _TICK, _REVERT, _departure(True, "d1", "2026-08-01T00:00:00Z"),
            _departure(False, "d2", "2026-08-08T00:00:00Z", z=3.2)]
    state = fold(rows)
    assert state["status"] == "active"
    assert state["latest_z"] == 3.2
    assert state["stress_departures"] == 1


@pytest.mark.parametrize("flag", [True, 1, "yes", 2.5])
def test_truthy_stress_values_are_recorded_not_state(flag):
    state = fold([_departure(flag)])
    assert state["status"] is None
    assert state["latest_z"] is None
    assert state["stress_departures"] == 1


@pytest.mark.parametrize("flag", [False, 0, None, ""])
def test_falsy_stress_values_activate(flag):
    state = fold([_departure(flag)])
    assert state["status"] == "active"
    assert state["latest_z"] == 9.9
    assert state["stress_departures"] == 0
