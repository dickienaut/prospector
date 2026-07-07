"""§4a xcorr — the LIVE lead-spawner driver (spec §9). `xcorr.scan` drives the proven M3 pipeline
once, reconstructs each pair's Schmitt state from the record (§9f), and steps ONE tick on the latest z
(the live analog of the backtest's per-day replay).

The gate here is the four load-bearing behaviors of a live spawner:
  1. FIRES live on a real sustained departure — a `lead.spawned` (shadow=false) that folds to an active,
     non-shadow lead (so it counts toward the §8a ceiling via active_nonshadow);
  2. stays silent on a null pair (no shared factor -> no spawn);
  3. obeys the stress gate (§4a CONTRACT) — a would-be entry on a crisis day is a stressed departure on
     `_system`, NEVER a spawn (the trigger is frozen);
  4. reconstructs state from the fossil record (§9f) — an already-active pair does not re-spawn; a
     reverted pair can re-enter.

Pure: prices in, events into a recorder — no store, no network, no clock. The planted panel reuses the
M3 fixture's construction (test_xcorr_math), but holds the shared factor ON through the end so the
LATEST row is mid-departure (the runner evaluates 'now', not a full replay)."""

import copy
from pathlib import Path

import numpy as np
import pandas as pd

from prospector.config import load_config
from prospector.fold.fold import active_nonshadow, fold
from prospector.sensors import xcorr
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-06T22:30:00Z"
# Synthetic series ids for the two sector constituents A/B (the panel's non-market columns). The lead
# keys on these (§2/§5). A 2-sector panel = exactly one pair (A×B), so specificity is unambiguous —
# no control-pair single-row noise to reason about (the M3 math tests already cover control pairs).
SID = {"A": "S000000001", "B": "S000000002"}
AB = xcorr_lead_id([SID["A"], SID["B"]])


def _planted_panel(n=1030, shift_on=1000, seed=166, loading=3.5, base_sd=0.008) -> pd.DataFrame:
    """A price panel (SPY market + A/B sectors) whose single pair A×B shares a residual factor from
    `shift_on` through the END, so the LATEST row is ~30 days into the departure — near the z peak,
    before the trailing baseline adapts (a scan evaluates 'now', not a full replay). n=shift_on+30
    lands z ≈ 4 at the last row (probed); loading=0 -> a null panel (no factor, last-row z < z_in)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    mkt = rng.normal(0, 0.01, n)
    common = rng.normal(0, base_sd, n)
    mask = np.zeros(n)
    mask[shift_on:] = 1.0
    rets = {"SPY": mkt}
    for k, beta in (("A", 1.1), ("B", 0.9)):
        rets[k] = beta * mkt + rng.normal(0, base_sd, n) + loading * common * mask
    return (1 + pd.DataFrame(rets, index=idx)).cumprod() * 100.0


def _recorder():
    events: list = []
    return events, events.append


# === 1. fires live on a sustained departure =========================================================

def test_scan_spawns_live_on_a_sustained_departure():
    cfg, _ = load_config(CONFIG)
    panel = _planted_panel()
    events, emit = _recorder()

    summary = xcorr.scan(panel, SID, cfg, NOW, {}, emit)

    spawns = [e for e in events if e["type"] == "lead.spawned"]
    assert len(spawns) == 1 and spawns[0]["lead"] == AB
    assert spawns[0]["payload"]["spawner"] == "xcorr"
    assert spawns[0]["payload"]["shadow"] is False                 # LIVE, never shadow
    assert any(e["type"] == "xcorr.departure" and e["lead"] == AB
               and e["payload"]["market_stress"] is False for e in events)
    # Folds to an ACTIVE, non-shadow lead -> counts toward the §8a ceiling by construction.
    state = fold([e for e in events if e["lead"] == AB])
    assert state["status"] == "active" and state["shadow"] is False
    assert active_nonshadow([state]) == [state]
    # Only the planted pair fires; the control pairs (A×C, B×C) do not.
    assert summary["spawned"] == ["A×B"]


# === 2. silent on a null pair =======================================================================

def test_scan_stays_silent_on_a_null_panel():
    cfg, _ = load_config(CONFIG)
    panel = _planted_panel(loading=0.0)  # no shared factor -> no pair sustains a departure
    events, emit = _recorder()

    summary = xcorr.scan(panel, SID, cfg, NOW, {}, emit)

    assert [e for e in events if e["type"] == "lead.spawned"] == []
    assert summary["spawned"] == []


# === 3. stress gate: a would-be entry is a stressed departure on _system, never a spawn =============

def test_scan_stress_gate_records_a_stressed_departure_not_a_spawn():
    cfg, _ = load_config(CONFIG)
    cfg = copy.deepcopy(cfg)
    cfg["xcorr"]["stress"]["crisis_level"] = 0.0  # every day counts as a crisis -> trigger frozen
    panel = _planted_panel()                       # A×B WOULD enter absent the gate
    events, emit = _recorder()

    xcorr.scan(panel, SID, cfg, NOW, {}, emit)

    assert [e for e in events if e["type"] == "lead.spawned"] == []          # frozen: no spawn
    stressed = [e for e in events if e["type"] == "xcorr.departure" and e["payload"]["market_stress"]]
    assert stressed and all(e["lead"] == SYSTEM_LEAD for e in stressed)      # recorded on _system
    assert any(e["payload"]["display"] == "A×B" for e in stressed)


# === 4. §9f: trigger state is reconstructed from the record =========================================

def test_scan_reconstructs_state_from_the_record():
    cfg, _ = load_config(CONFIG)
    panel = _planted_panel()

    # Already active (last trigger event a departure): the pair does NOT re-spawn — it ticks.
    ev_active, emit_active = _recorder()
    xcorr.scan(panel, SID, cfg, NOW, {AB: "xcorr.departure"}, emit_active)
    assert [e for e in ev_active if e["type"] == "lead.spawned"] == []
    assert any(e["type"] == "xcorr.tick" and e["lead"] == AB for e in ev_active)

    # Reverted (last trigger event a revert -> quiet): the pair CAN re-enter -> spawns.
    ev_rev, emit_rev = _recorder()
    xcorr.scan(panel, SID, cfg, NOW, {AB: "xcorr.reverted"}, emit_rev)
    assert any(e["type"] == "lead.spawned" and e["lead"] == AB for e in ev_rev)
