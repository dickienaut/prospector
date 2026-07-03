"""Dispersion driver + the generous payload (spec §4b, rev8 CONTRACT). Offline.

Proves the three load-bearing behaviors: (1) an entry emits a shadow-wired lead.spawned + a
dispersion.tick, and the tick carries the FULL generous structure the deferred v2 proto-cluster
layer needs (membership + sub-cluster assignment + correlation structure), not just scalar Q;
(2) the payload survives canonical_json(allow_nan=False) — every NaN became null; (3) folding the
events yields an active-but-shadow lead that active_nonshadow excludes from the oracle."""

import numpy as np
import pandas as pd
import pytest

from prospector.fold.fold import active_nonshadow, fold
from prospector.ingest.holdings import MembershipSnapshot
from prospector.sensors import dispersion
from prospector.store.envelope import canonical_json

NOW = "2026-07-14T22:30:00Z"
XLK_SERIES = "S000006415"


def _panel(fractured: bool, n_days=340, split_at=270, seed=0):
    """A six-constituent PRICE panel. fractured=True has a late two-block fracture (Q departs);
    fractured=False stays a single common-factor block (Q ~ 0, no departure)."""
    rng = np.random.default_rng(seed)
    ids = ["A1", "A2", "A3", "B1", "B2", "B3"]
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    common = rng.normal(0, 0.010, n_days)
    fac = {"A": rng.normal(0, 0.012, n_days), "B": rng.normal(0, 0.012, n_days)}
    data = {}
    for cid in ids:
        idio = rng.normal(0, 0.002, n_days)
        r = common + idio
        if fractured:
            block = np.zeros(n_days)
            block[split_at:] = fac[cid[0]][split_at:]
            r = r + block
        data[cid] = r
    prices = (1 + pd.DataFrame(data, index=dates)).cumprod() * 100.0
    return ids, prices


def _membership(ids):
    # Descending weights so the top-weighted constituent is column 0 (the bipartition canonical key).
    weights = [0.30, 0.22, 0.16, 0.13, 0.11, 0.08][:len(ids)]
    members = [{"name": f"NAME {i}", "identifier": i, "weight": w, "sector": "Information Technology"}
               for i, w in zip(ids, weights)]
    return MembershipSnapshot(series_id=XLK_SERIES, ticker="XLK", as_of="2026-07-13", source="spdr",
                              members=members, coverage_target=0.90, coverage_actual=0.92)


def _cfg(z_in, z_out, detail="full", paging=False, top_k=40):
    return {"dispersion": {"z_in": z_in, "z_out": z_out, "paging": paging, "window_days": 63,
                           "baseline_days": 252, "min_constituents": 4, "method": "spectral",
                           "tick_cadence_days": 7, "correlation_detail": detail,
                           "correlation_top_k": top_k}}


def _latest_z(prices, cfg):
    returns = dispersion.constituent_returns(prices)
    q = dispersion.dispersion_q_series(returns, 63, 4)
    z = dispersion.dispersion_z(q, 252).dropna()
    return float(z.iloc[-1])


def _fold_ready(events):
    """The driver emits envelope dicts without an event_id (append assigns it); the fold needs one."""
    return [{**e, "event_id": f"ev{i}"} for i, e in enumerate(events)]


# -- entry: shadow spawn + generous tick --------------------------------------

def test_entry_emits_shadow_spawn_and_generous_tick():
    ids, prices = _panel(fractured=True)
    z = _latest_z(prices, _cfg(2.5, 1.0))
    assert z >= 2.5, f"expected a fracture departure, got z={z}"  # the panel really does fracture
    cfg = _cfg(z_in=z * 0.9, z_out=1.0)  # thresholds bracket the real z so the driver enters

    events = []
    result = dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, cfg, NOW,
                             last_event_type=None, emit=events.append)

    assert result["edge"] == "entered"
    assert [e["type"] for e in events] == ["lead.spawned", "dispersion.tick"]

    spawn = events[0]["payload"]
    assert spawn["spawner"] == "dispersion" and spawn["shadow"] is True
    assert spawn["series_id"] == XLK_SERIES

    tick = events[1]["payload"]
    # --- the rev8 §4b CONTRACT: generous, not scalar-only ---
    assert tick["q"] is not None and tick["z"] is not None
    # (a) full constituent membership + each name's sub-cluster assignment
    assert set(tick["split_membership"]) == set(ids)
    assert set(tick["split_membership"].values()) == {0, 1}       # a real two-block split
    # (b) per-cluster centroids
    assert len(tick["clusters"]) == 2
    for c in tick["clusters"]:
        assert c["medoid"] in ids and c["mean_within_corr"] is not None
        assert {m["identifier"] for m in c["members"]}                # membership listed per cluster
    covered = {m["identifier"] for c in tick["clusters"] for m in c["members"]}
    assert covered == set(ids)                                       # every name placed
    # (c) constituent correlation structure
    assert tick["correlation"]["detail"] == "full"
    assert set(tick["correlation"]["within_cluster"]) == {"0", "1"}
    assert tick["correlation"]["between_cluster"] is not None
    assert tick["correlation"]["matrix"]["labels"] == ids
    assert len(tick["correlation"]["matrix"]["values"]) == len(ids)


def test_generous_payload_survives_canonical_json():
    """canonical_json uses allow_nan=False: a bare NaN anywhere in the payload would be rejected at
    write time. The payload builder must have turned every NaN into null."""
    ids, prices = _panel(fractured=True)
    z = _latest_z(prices, _cfg(2.5, 1.0))
    events = []
    dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, _cfg(z * 0.9, 1.0), NOW,
                    None, events.append)
    for e in events:
        canonical_json(e["payload"])  # raises ValueError on any NaN/inf


def test_folded_lead_is_active_but_shadow_excluded_from_oracle():
    ids, prices = _panel(fractured=True)
    z = _latest_z(prices, _cfg(2.5, 1.0))
    events = []
    dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, _cfg(z * 0.9, 1.0), NOW,
                    None, events.append)
    state = fold(_fold_ready(events))
    assert state["status"] == "active"
    assert state["shadow"] is True
    assert state["spawner"] == "dispersion"
    # THE contract: a shadow lead never reaches the ceiling/paging/digest (spec §4b, test 3).
    assert active_nonshadow([state]) == []


# -- the correlation_detail knob ----------------------------------------------

@pytest.mark.parametrize("detail,has_matrix,has_pairs", [
    ("full", True, True), ("topk", False, True), ("summary", False, False)])
def test_correlation_detail_knob(detail, has_matrix, has_pairs):
    ids, prices = _panel(fractured=True)
    z = _latest_z(prices, _cfg(2.5, 1.0))
    events = []
    dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices,
                    _cfg(z * 0.9, 1.0, detail=detail, top_k=5), NOW, None, events.append)
    corr = events[1]["payload"]["correlation"]
    assert corr["detail"] == detail
    assert ("matrix" in corr) is has_matrix
    assert ("top_pairs" in corr) is has_pairs
    # The within/between summaries are ALWAYS present, whatever the detail level.
    assert corr["within_cluster"] and corr["between_cluster"] is not None


# -- no false entry, and the exit path ----------------------------------------

def test_calm_basket_does_not_enter():
    ids, prices = _panel(fractured=False)
    events = []
    result = dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, _cfg(2.5, 1.0), NOW,
                             last_event_type=None, emit=events.append)
    assert result["edge"] is None
    assert events == []  # a single-block basket never spawns


def test_active_lead_reverts_when_z_falls():
    ids, prices = _panel(fractured=False)          # calm basket -> low z
    z = _latest_z(prices, _cfg(2.5, 1.0))
    # Thresholds put the calm z at/below the exit so an ACTIVE lead reverts (Schmitt exit).
    cfg = _cfg(z_in=z + 2.0, z_out=z)
    events = []
    result = dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, cfg, NOW,
                             last_event_type="dispersion.tick", emit=events.append)
    assert result["edge"] == "exited"
    assert [e["type"] for e in events] == ["dispersion.reverted"]
    assert events[0]["payload"]["series_id"] == XLK_SERIES


def test_tick_only_emitted_while_active_when_cadence_due():
    ids, prices = _panel(fractured=True)
    z = _latest_z(prices, _cfg(2.5, 1.0))
    # Already active (last event a tick), z stays above z_out so no edge: a tick fires only if due.
    cfg = _cfg(z_in=z + 2.0, z_out=1.0)
    not_due = []
    dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, cfg, NOW,
                    last_event_type="dispersion.tick", emit=not_due.append, tick_due=False)
    assert not_due == []
    due = []
    dispersion.scan(XLK_SERIES, "XLK", _membership(ids), prices, cfg, NOW,
                    last_event_type="dispersion.tick", emit=due.append, tick_due=True)
    assert [e["type"] for e in due] == ["dispersion.tick"]
