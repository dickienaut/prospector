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
    """Reconstruct trigger state from the last TRIGGER-RELEVANT recorded event for an entity (§9).
    Quiet only when there is no prior event (`None`) or the last one was a `.reverted` exit;
    everything else — the spawn, a `.departure`, or a cadence `.tick` — means the entity is still
    in departure, i.e. active.

    Why not "only `.departure` is active" (the original form): dispersion has NO `.departure` event
    (spec §5: only `dispersion.tick` / `dispersion.reverted`), so under the old rule an actively
    *ticking* dispersion lead would reconstruct as quiet and re-spawn every run. The `.reverted`
    suffix is the single exit convention (matching the fold, which folds any `*.reverted` to
    `status=reverted`), so keying off it is correct for BOTH sensors — xcorr
    (departure/tick→active, reverted→quiet) and dispersion (spawn/tick→active, reverted→quiet).

    Contract: the caller passes the last event whose type belongs to the sensor's own trigger
    vocabulary (`lead.spawned` / `*.departure` / `*.tick` / `*.reverted`). Corroboration
    (`rebalance`, `launch`), `verdict`, and `capture.stored` accrete onto a lead without changing
    its trigger state, so the driver skips them when selecting `last_type` — otherwise a
    verdict-after-revert would wrongly read as active. (Dispersion's stress-free stream makes this
    a non-issue in practice, but the contract keeps a future caller honest.)"""
    if last_type is None or last_type.endswith(".reverted"):
        return QUIET
    return ACTIVE
