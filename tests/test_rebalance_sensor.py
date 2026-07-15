"""Rebalance sensor (spec §4d, milestone 4 — holdings-diff accretion core).

A watched fund's daily holdings are diffed vs the prior pull; a material change (any add/drop of an
identified security, or a weight delta ≥ threshold) accretes a `rebalance` onto every live lead whose
baskets include that fund (forward-hash routing, CONTRACT §4d), else onto `_system`. Rebalance is an
accretion sensor — no Schmitt, no lead of its own; the fold treats `rebalance` as a silent
corroboration. Cash/derivative rows (no CUSIP) never fire. Live-lead enumeration reads the registry's
materialized snapshots (CONTRACT §4d), never a re-fold or a cache. Offline throughout."""

import pandas as pd

from prospector.fold.fold import fold
from prospector.fold.snapshots import write_snapshot
from prospector.sensors import rebalance
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.event_store import EventStore

NOW = "2026-07-03T22:30:00Z"
T0 = "2026-07-01T00:00:00Z"
T1 = "2026-07-02T00:00:00Z"


def _frame(rows):
    return pd.DataFrame(rows, columns=["name", "identifier", "weight", "sector"])


# -- diff: adds / drops / threshold weight moves / cash exclusion ----------------------------

def test_identified_excludes_a_nan_identifier_no_phantom_security():
    # S5: a pandas NaN identifier stringifies to "nan" (truthy), which the `not ident` guard would treat as
    # a REAL security — a phantom position whose daily wiggle could fire a spurious rebalance. The pd.isna
    # guard routes NaN -> "" -> excluded, exactly like a blank identifier.
    import numpy as np
    frame = _frame([
        {"name": "AAA", "identifier": "111", "weight": 0.50, "sector": "T"},
        {"name": "Mystery", "identifier": np.nan, "weight": 0.50, "sector": "T"},
    ])
    ident = rebalance._identified(frame)
    assert "nan" not in ident
    assert set(ident) == {"111"}


def test_diff_detects_adds_drops_and_threshold_weight_moves():
    prior = _frame([
        {"name": "AAA", "identifier": "111", "weight": 0.20, "sector": "T"},
        {"name": "BBB", "identifier": "222", "weight": 0.10, "sector": "T"},
        {"name": "CCC", "identifier": "333", "weight": 0.05, "sector": "T"},   # dropped in current
        {"name": "CASH", "identifier": "", "weight": 0.03, "sector": ""},      # unidentified -> ignored
    ])
    current = _frame([
        {"name": "AAA", "identifier": "111", "weight": 0.26, "sector": "T"},   # +0.06 -> a delta
        {"name": "BBB", "identifier": "222", "weight": 0.103, "sector": "T"},  # +0.003 -> below 0.5%
        {"name": "DDD", "identifier": "444", "weight": 0.04, "sector": "T"},   # an add
        {"name": "CASH", "identifier": "", "weight": 0.05, "sector": ""},      # a cash wiggle -> ignored
    ])
    d = rebalance.diff_holdings(prior, current, threshold=0.005)
    assert [a["identifier"] for a in d["adds"]] == ["444"]
    assert [x["identifier"] for x in d["drops"]] == ["333"]
    assert [w["identifier"] for w in d["weight_deltas"]] == ["111"]  # AAA only; BBB's +0.3% is sub-threshold
    assert d["weight_deltas"][0]["delta"] == 0.06
    assert d["material"] is True


def test_identical_holdings_are_not_material():
    f = _frame([{"name": "AAA", "identifier": "111", "weight": 0.5, "sector": "T"}])
    assert rebalance.diff_holdings(f, f, 0.005)["material"] is False


def test_cash_only_wiggle_without_identifier_never_fires():
    prior = _frame([{"name": "CASH", "identifier": "", "weight": 0.02, "sector": ""}])
    current = _frame([{"name": "CASH", "identifier": "", "weight": 0.09, "sector": ""}])  # +7% but no CUSIP
    assert rebalance.diff_holdings(prior, current, 0.005) == {
        "adds": [], "drops": [], "weight_deltas": [], "material": False}


# -- routing: forward-hash the fund's pairs + basket, intersect with active leads -------------

def test_watching_leads_forward_hashes_pairs_and_basket():
    universe = ["S1", "S2", "S3", "S4"]
    fund = "S2"
    disp = dispersion_lead_id("S2")
    pair_21 = xcorr_lead_id(["S2", "S1"])     # the real functions -> equality holds by construction
    pair_23 = xcorr_lead_id(["S2", "S3"])
    active = {disp, pair_21, "xcorr-unrelated", dispersion_lead_id("S9")}
    got = rebalance.watching_leads(fund, universe, active)
    assert set(got) == {disp, pair_21}        # pair_23 not active; unrelated leads excluded
    assert got == sorted(got)                 # deterministic order
    assert pair_23 not in got
    # a fund whose leads are all reverted/absent routes nowhere
    assert rebalance.watching_leads("S1", universe, {dispersion_lead_id("S9")}) == []


# -- scan: emit onto matched live leads, else _system; silent on immaterial ------------------

def _add_frames():
    prior = _frame([{"name": "AAA", "identifier": "111", "weight": 0.20, "sector": "T"}])
    current = _frame([{"name": "AAA", "identifier": "111", "weight": 0.20, "sector": "T"},
                      {"name": "BBB", "identifier": "222", "weight": 0.05, "sector": "T"}])  # an add
    return prior, current


CFG = {"rebalance": {"weight_delta_threshold": 0.005}}


def test_scan_emits_rebalance_onto_matched_live_leads():
    universe = ["S1", "S2", "S3"]
    pair = xcorr_lead_id(["S2", "S1"])
    prior, current = _add_frames()
    events = []
    res = rebalance.scan("S2", "XLF", prior, current, universe, {pair}, CFG, NOW,
                         events.append, as_of="2026-07-03")
    assert res["material"] and res["targets"] == [pair] and res["emitted_to"] == [pair]
    assert res["n_adds"] == 1 and res["n_drops"] == 0 and res["n_weight_deltas"] == 0
    (ev,) = events
    assert ev["lead"] == pair and ev["type"] == "rebalance" and ev["schema"] == 1
    assert ev["payload"]["series_id"] == "S2" and ev["payload"]["as_of"] == "2026-07-03"
    assert [a["identifier"] for a in ev["payload"]["adds"]] == ["222"]


def test_scan_with_no_live_lead_records_on_system():
    prior, current = _add_frames()
    events = []
    res = rebalance.scan("S2", "XLF", prior, current, ["S1", "S2", "S3"], set(), CFG, NOW,
                         events.append)
    assert res["material"] and res["targets"] == [] and res["emitted_to"] == ["_system"]
    (ev,) = events
    assert ev["lead"] == "_system"  # kept in the record, not surfaced


def test_scan_immaterial_change_emits_nothing():
    f = _frame([{"name": "AAA", "identifier": "111", "weight": 0.5, "sector": "T"}])
    events = []
    res = rebalance.scan("S2", "XLF", f, f, ["S1", "S2"], {xcorr_lead_id(["S1", "S2"])}, CFG, NOW,
                         events.append)
    assert res["material"] is False and events == []


# -- fold: a rebalance is a silent corroboration (no status change, no paging) ----------------

def test_rebalance_accretes_as_silent_corroboration():
    rows = [
        {"event_id": "e1", "ts": T0, "lead": "xcorr-abc", "type": "lead.spawned",
         "payload": {"spawner": "xcorr", "display": "X×Y", "shadow": False}, "schema": 1},
        {"event_id": "e2", "ts": T1, "lead": "xcorr-abc", "type": "rebalance",
         "payload": {"series_id": "S2", "adds": [{"identifier": "222"}], "drops": [],
                     "weight_deltas": []}, "schema": 1},
    ]
    state = fold(rows)
    assert state["status"] == "active"                                   # rebalance never flips status
    assert [c["type"] for c in state["corroborations"]] == ["rebalance"]


# -- enumeration: active-nonshadow read from the registry-materialized snapshots (CONTRACT) ----

def test_active_nonshadow_lead_ids_reads_materialized_snapshots(layout, registry):
    store = EventStore(layout, registry, clock=lambda: NOW)

    def spawn(lead, spawner, shadow):
        store.append({"ts": T0, "lead": lead, "type": "lead.spawned",
                      "payload": {"spawner": spawner, "display": lead, "shadow": shadow}, "schema": 1})

    spawn("xcorr-active", "xcorr", False)        # active, non-shadow -> counts
    spawn("disp-shadow", "dispersion", True)     # active but shadow -> excluded
    spawn("xcorr-reverted", "xcorr", False)      # active then reverted -> excluded
    store.append({"ts": T1, "lead": "xcorr-reverted", "type": "xcorr.reverted",
                  "payload": {"display": "xcorr-reverted"}, "schema": 1})

    # Materialize each lead's fold as a snapshot — the registry-indexed state the adapter reads.
    for lead in ("xcorr-active", "disp-shadow", "xcorr-reverted"):
        write_snapshot(layout, registry, lead, fold(registry.events_for_lead(lead)),
                       reason="test", ts=NOW)

    assert rebalance.active_nonshadow_lead_ids(registry, layout) == {"xcorr-active"}
