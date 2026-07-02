"""Backtest separation is structural, not conventional (spec §7, CONTRACT): synthetic history
lives under backtest/ with its own store root and registry, and can never land under the live
events/ tree."""

import pytest

from prospector.primitives.atomic import sha256_file
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout, backtest_run_root
from prospector.store.registry import Registry


def make_event(i, **over):
    e = {"ts": f"2026-07-14T13:00:0{i}Z", "lead": "lead_abc123", "type": "xcorr.tick",
         "payload": {"z": float(i)}, "schema": 1}
    e.update(over)
    return e


def _tree_hashes(root):
    return {p.relative_to(root).as_posix(): sha256_file(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_live_root_under_backtest_rejected(tmp_path):
    with pytest.raises(ValueError):
        StoreLayout(tmp_path / "backtest" / "run_x", kind="live")
    with pytest.raises(ValueError):
        StoreLayout(backtest_run_root(tmp_path / "store", "x"))  # kind defaults to 'live'


def test_backtest_root_requires_backtest_dir(tmp_path):
    with pytest.raises(ValueError):
        StoreLayout(tmp_path / "store", kind="backtest")
    # The sanctioned construction path does not raise.
    StoreLayout(backtest_run_root(tmp_path / "store", "x"), kind="backtest")


def test_backtest_writes_leave_live_events_byte_identical(store_root, layout, registry):
    live = EventStore(layout, registry)
    for i in range(3):
        live.append(make_event(i))
    before = _tree_hashes(layout.events_root())
    assert len(before) == 3  # sanity: the live record exists to be protected

    bt_layout = StoreLayout(backtest_run_root(store_root, "test"), kind="backtest")
    bt_registry = Registry(bt_layout.registry_path())
    try:
        bt = EventStore(bt_layout, bt_registry)
        for i in range(3):
            bt.append(make_event(i, type="xcorr.departure"))
        assert len(bt.read_lead("lead_abc123")) == 3
    finally:
        bt_registry.close()

    # The live fossil record is byte-identical: same files, same hashes, nothing added.
    assert _tree_hashes(layout.events_root()) == before

    # The synthetic events landed under backtest/, in the run's own tree.
    assert bt_layout.events_root().is_relative_to(store_root / "backtest" / "run_test")
    assert len(_tree_hashes(bt_layout.events_root())) == 3
