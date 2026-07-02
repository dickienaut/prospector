"""Schmitt trigger — the shared hysteresis state machine for the departure sensors (spec §4).

Both 4a (excess-correlation) and 4b (dispersion) gate their z on the same two-threshold trigger:
entry at z >= z_in, exit at z <= z_out, with z_in > z_out so a z hovering between the two
thresholds cannot flap the lead in and out. "Record on cadence, push on state change" (§4) —
this machine is the state-change detector; the tick cadence lives in the runner.

Per-run statelessness (§9): the runner holds no state between runs except the store, so the
per-pair trigger state is reconstructed from the last recorded event for that pair before the
first z of the new run is stepped in.
"""

from __future__ import annotations

import math

QUIET = "quiet"
ACTIVE = "active"


def step(state: str, z: float | None, z_in: float, z_out: float) -> tuple[str, str | None]:
    """Advance the trigger one z. Returns (new_state, edge) where edge is 'entered', 'exited',
    or None. A None/NaN z (a not-yet-warmed baseline) never transitions — warmup safety, so a
    partial window can't spawn a phantom lead."""
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return state, None
    if state == QUIET and z >= z_in:
        return ACTIVE, "entered"
    if state == ACTIVE and z <= z_out:
        return QUIET, "exited"
    return state, None


def state_from_last_event_type(last_type: str | None) -> str:
    """Reconstruct trigger state from the last recorded event type for a pair (§9). A pair
    whose last event was a `.departure` is active; anything else (a `.reverted`, or no prior
    event at all) is quiet."""
    if last_type is not None and last_type.endswith(".departure"):
        return ACTIVE
    return QUIET
