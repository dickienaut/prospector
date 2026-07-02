"""Schmitt trigger — the shared hysteresis state machine (spec §4). Entry at z>=z_in, exit at
z<=z_out, z_in>z_out so a z hovering between the thresholds cannot flap the lead in and out. A
not-yet-warmed baseline (None/NaN z) never transitions — warmup safety. State is reconstructed
from the last recorded event type (§9, per-run statelessness)."""

import math

from prospector.sensors.schmitt import (ACTIVE, QUIET, state_from_last_event_type, step)

Z_IN = 2.5
Z_OUT = 1.0


# -- step: the two edges ------------------------------------------------------

def test_entry_from_quiet_at_or_above_z_in():
    assert step(QUIET, 2.5, Z_IN, Z_OUT) == (ACTIVE, "entered")  # inclusive at z_in
    assert step(QUIET, 3.0, Z_IN, Z_OUT) == (ACTIVE, "entered")


def test_no_entry_from_quiet_below_z_in():
    assert step(QUIET, 2.49, Z_IN, Z_OUT) == (QUIET, None)
    # In the hysteresis band (between z_out and z_in): a quiet lead stays quiet.
    assert step(QUIET, 1.5, Z_IN, Z_OUT) == (QUIET, None)


def test_exit_from_active_at_or_below_z_out():
    assert step(ACTIVE, 1.0, Z_IN, Z_OUT) == (QUIET, "exited")  # inclusive at z_out
    assert step(ACTIVE, 0.5, Z_IN, Z_OUT) == (QUIET, "exited")
    assert step(ACTIVE, -2.0, Z_IN, Z_OUT) == (QUIET, "exited")


def test_no_exit_from_active_above_z_out():
    assert step(ACTIVE, 1.01, Z_IN, Z_OUT) == (ACTIVE, None)
    # In the hysteresis band: an active lead stays active.
    assert step(ACTIVE, 2.0, Z_IN, Z_OUT) == (ACTIVE, None)


# -- the hysteresis promise: no flapping --------------------------------------

def test_z_oscillating_inside_the_band_forever_yields_zero_edges():
    """A z that bounces between z_out+0.2 and z_in-0.2 (inside the band, both ways) must never
    produce an edge from either state — this is the whole reason for two thresholds."""
    low, high = Z_OUT + 0.2, Z_IN - 0.2  # 1.2 and 2.3, both strictly inside the band
    for start in (QUIET, ACTIVE):
        state = start
        edges = []
        for i in range(1000):
            z = high if i % 2 == 0 else low
            state, edge = step(state, z, Z_IN, Z_OUT)
            if edge is not None:
                edges.append(edge)
        assert edges == []
        assert state == start  # never left its starting state


# -- warmup safety: None / NaN never transition -------------------------------

def test_none_z_never_transitions_from_either_state():
    assert step(QUIET, None, Z_IN, Z_OUT) == (QUIET, None)
    assert step(ACTIVE, None, Z_IN, Z_OUT) == (ACTIVE, None)


def test_nan_z_never_transitions_from_either_state():
    nan = float("nan")
    assert math.isnan(nan)
    assert step(QUIET, nan, Z_IN, Z_OUT) == (QUIET, None)
    assert step(ACTIVE, nan, Z_IN, Z_OUT) == (ACTIVE, None)


# -- state reconstruction from the fossil record (§9) -------------------------

def test_state_from_last_event_type():
    assert state_from_last_event_type("xcorr.departure") == ACTIVE
    assert state_from_last_event_type("xcorr.reverted") == QUIET
    assert state_from_last_event_type(None) == QUIET
    # Any other/unknown type reconstructs to quiet (only a .departure means active).
    assert state_from_last_event_type("xcorr.tick") == QUIET
    assert state_from_last_event_type("lead.spawned") == QUIET
    assert state_from_last_event_type("dispersion.departure") == ACTIVE  # any *.departure
