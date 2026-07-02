"""Shadow discipline (spec §4b, CONTRACT): a shadow lead folds shadow=True from its
lead.spawned payload, and active_nonshadow is THE single filter the ceiling counter, paging,
and the email digest call — so shadow leads are excluded from all oracle-facing surfaces by
construction (spec test 3: shadow flags respected in ceiling/paging logic)."""

from __future__ import annotations

import pytest

from prospector.fold.fold import active_nonshadow, fold, state_changed


def _spawn(shadow, lead="ld_sh", **extra):
    payload = {"spawner": "dispersion", "display": "XLE split", **extra}
    if shadow is not ...:
        payload["shadow"] = shadow
    return {"event_id": f"sp_{lead}", "ts": "2026-07-01T00:00:00Z",
            "type": "lead.spawned", "payload": payload, "lead": lead, "schema": 1}


def _revert(lead="ld_sh"):
    return {"event_id": f"rv_{lead}", "ts": "2026-07-10T00:00:00Z",
            "type": "dispersion.reverted", "payload": {"z": 0.5}, "lead": lead,
            "schema": 1}


def _depart(lead="ld_sh"):
    return {"event_id": f"dp_{lead}", "ts": "2026-07-20T00:00:00Z",
            "type": "xcorr.departure", "payload": {"z": 2.8}, "lead": lead, "schema": 1}


def test_shadow_flag_comes_from_spawn_payload():
    state = fold([_spawn(True)])
    assert state["status"] == "active"
    assert state["shadow"] is True
    assert state["spawner"] == "dispersion"


def test_shadow_defaults_false_when_absent():
    assert fold([_spawn(...)])["shadow"] is False


@pytest.mark.parametrize("value,expected", [
    (True, True), (1, True), ("y", True),
    (False, False), (0, False), (None, False),
])
def test_shadow_is_folded_as_bool(value, expected):
    assert fold([_spawn(value)])["shadow"] is expected


def test_shadow_spawn_is_a_status_and_shadow_change():
    state = fold([_spawn(True)])
    assert state_changed(None, state) == ["status", "shadow"]
    assert state_changed(None, fold([_spawn(False)])) == ["status"]


def test_active_nonshadow_filters_mixed_collection():
    active_clear = fold([_spawn(False, "ld_a")])
    active_shadow = fold([_spawn(True, "ld_b")])
    reverted_clear = fold([_spawn(False, "ld_c"), _revert("ld_c")])
    reverted_shadow = fold([_spawn(True, "ld_d"), _revert("ld_d")])
    fresh = fold([])
    collection = [active_shadow, reverted_clear, active_clear, reverted_shadow, fresh]
    assert active_nonshadow(collection) == [active_clear]
    assert active_nonshadow([]) == []


def test_reactivated_nonshadow_lead_reenters_the_filter():
    reverted = fold([_spawn(False, "ld_e"), _revert("ld_e")])
    reactivated = fold([_spawn(False, "ld_e"), _revert("ld_e"), _depart("ld_e")])
    assert active_nonshadow([reverted]) == []
    assert active_nonshadow([reactivated]) == [reactivated]


def test_shadow_lead_stays_excluded_even_when_active_and_ticking():
    state = fold([
        _spawn(True, "ld_f"),
        {"event_id": "tk_ld_f", "ts": "2026-07-08T00:00:00Z",
         "type": "dispersion.tick", "payload": {"z": 3.3}, "lead": "ld_f", "schema": 1},
    ])
    assert state["status"] == "active"
    assert state["latest_z"] == 3.3
    assert active_nonshadow([state]) == []
