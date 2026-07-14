"""M6 discourse capture — acceptance tests (spec §6; build note §5). Every test attempts the VIOLATION.

OFFLINE (CLAUDE.md): the CaptureProvider's `call`/`fetch` seams are closed over in-memory fixtures, so
no test opens a socket (the conftest network guard fails any real connection). The invariants under test
are the load-bearing ones: the WALL (only result blocks + fetched text ever hit disk — never model
prose), the HARD budget cap (pause + operational fault, never a silent overrun/skip), shadow leads never
capture, deterministic query construction, the per-lead weekly gate, and backup carrying the captures
tree.
"""

import json
from pathlib import Path
from types import SimpleNamespace

from prospector.fold.fold import fold
from prospector.fold.snapshots import write_snapshot
from prospector.ingest.capture import (CaptureBudget, CaptureProvider, build_queries, capture_prefix,
                                        period_keys, top_urls)
from prospector.runner.runlog import RunLog
from prospector.runner.runner import _capture_due, _capture_meta, _run_capture
from prospector.store.backup import DEFAULT_MARKER, backup_store
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

NOW = "2026-07-13T12:00:00Z"
# The distinctive model prose the fake provider emits — it must NEVER appear in the captures tree.
PROSE = "SECRET_MODEL_PROSE_that_must_never_be_persisted"


def _fake_call(body: dict) -> dict:
    """Echo the requested (line-2) query into the server_tool_use (so query_issued == our query —
    determinism), return two web_search_result blocks, AND a model `text` block that must be dropped."""
    query = body["messages"][0]["content"].splitlines()[1]
    return {"content": [
        {"type": "server_tool_use", "id": "srv1", "name": "web_search", "input": {"query": query}},
        {"type": "web_search_tool_result", "tool_use_id": "srv1", "content": [
            {"type": "web_search_result", "title": "A", "url": "https://ex.com/a", "encrypted_content": "E1"},
            {"type": "web_search_result", "title": "B", "url": "https://ex.com/b", "encrypted_content": "E2"}]},
        {"type": "text", "text": PROSE}]}


def _fake_fetch(url: str) -> bytes:
    return f"<html><body><p>page text for {url}</p><script>{PROSE}</script></body></html>".encode()


def _provider(call=None, fetch=None):
    return CaptureProvider("test-key", model="claude-haiku-4-5",
                           call=call or _fake_call, fetch=fetch or _fake_fetch)


def _cfg(**over) -> dict:
    cap = {"k_queries": 5, "top_n": 5, "m_fetch_urls": 2, "max_searches_per_week": 60,
           "unit_price_usd": 0.01, "model": "claude-haiku-4-5", "monthly_budget_usd": 10}
    cap.update(over)
    return {"capture": cap}


def _store(tmp_path):
    layout = StoreLayout(tmp_path)
    registry = Registry(layout.registry_path())
    return layout, registry, EventStore(layout, registry)


def _seed_lead(layout, registry, store, lead, *, shadow=False, display="XLK basket",
               dispersion=True, ts=NOW):
    """Seed a materialized ACTIVE lead so active_nonshadow_lead_ids finds it (spawn event -> fold ->
    snapshot). A dispersion lead also carries a dispersion.tick payload (constituent names for queries)."""
    store.append({"ts": ts, "lead": lead, "type": "lead.spawned",
                  "payload": {"spawner": "dispersion" if dispersion else "xcorr", "display": display,
                              "shadow": shadow, "spawned_at": ts}, "schema": 1})
    if dispersion:
        store.append({"ts": ts, "lead": lead, "type": "dispersion.tick",
                      "payload": {"clusters": [{"members": [
                          {"name": "Alpha Corp", "identifier": "A", "weight": 0.30},
                          {"name": "Beta Inc", "identifier": "B", "weight": 0.20}]}]}, "schema": 1})
    state = fold(registry.events_for_lead(lead))
    write_snapshot(layout, registry, lead, state, "state_change", ts)


def _deps(layout, registry, provider, cfg):
    return SimpleNamespace(layout=layout, registry=registry, capture_provider=provider, cfg=cfg)


# --- pure functions ------------------------------------------------------------------------------

def test_build_queries_deterministic_and_ordered():
    meta = {"display": "XLK x XLU", "industries": ["Semiconductors"],
            "constituents": ["NVDA", "AAPL", "NVDA", "MSFT"]}
    q1 = build_queries(meta, 5, 5)
    q2 = build_queries(meta, 5, 5)
    assert q1 == q2                                   # identical meta -> identical query set
    assert q1 == ["XLK x XLU", "Semiconductors", "NVDA", "AAPL", "MSFT"]  # ordered, de-duped
    assert build_queries(meta, 2, 5) == ["XLK x XLU", "Semiconductors"]   # truncated to K
    assert build_queries({"constituents": ["a", "b", "c"]}, 5, 2) == ["a", "b"]  # top_n limit
    # no timestamps/randomness leak into the query text
    assert all("2026" not in q for q in q1)


def test_top_urls_first_m_distinct_and_error_block_safe():
    blocks = [
        {"type": "web_search_tool_result", "content": [{"url": "u1"}, {"url": "u2"}, {"url": "u1"}]},
        {"type": "web_search_tool_result", "content": {"error_code": "max_uses_exceeded"}},  # error: dict
        {"type": "web_search_tool_result", "content": [{"url": "u3"}]}]
    assert top_urls(blocks, 2) == ["u1", "u2"]
    assert top_urls(blocks, 9) == ["u1", "u2", "u3"]


def test_provider_search_keeps_only_result_blocks_drops_prose():
    """The WALL at the provider boundary: search() returns result blocks + the issued query, never the
    model's text block."""
    res = _provider().search("some query")
    assert res["query"] == "some query"
    assert res["query_issued"] == "some query"        # determinism: model ran our verbatim query
    assert [b["type"] for b in res["result_blocks"]] == ["web_search_tool_result"]
    assert PROSE not in json.dumps(res["result_blocks"])   # prose dropped


def test_capture_budget_counter_persists_and_increments(tmp_path):
    _, registry, _ = _store(tmp_path)
    budget = CaptureBudget(registry)
    wk, mo = period_keys(NOW)
    assert budget.count("week", wk) == 0
    budget.record_search(wk, mo, NOW)
    budget.record_search(wk, mo, NOW)
    assert budget.count("week", wk) == 2 and budget.count("month", mo) == 2
    registry.close()
    # survives a restart (persisted, not in-memory) — build note §3b
    registry2 = Registry((tmp_path / "registry.sqlite"))
    assert CaptureBudget(registry2).count("week", wk) == 2


def test_capture_due_weekly_gate():
    assert _capture_due({"capture_inventory": []}, NOW) is True            # never captured -> due
    assert _capture_due({"capture_inventory": [{"ts": "2026-07-10T12:00:00Z"}]}, NOW) is False  # 3d ago
    assert _capture_due({"capture_inventory": [{"ts": "2026-07-05T12:00:00Z"}]}, NOW) is True   # 8d ago
    # newest entry governs (a stale entry beside a recent one -> not due)
    assert _capture_due({"capture_inventory": [{"ts": "2026-06-01T12:00:00Z"},
                                               {"ts": "2026-07-12T12:00:00Z"}]}, NOW) is False


# --- integration: _run_capture over a seeded store ----------------------------------------------

def test_capture_stores_only_result_and_fetch_blocks(tmp_path):
    """The WALL end-to-end: a capture writes result blocks + fetched page text to captures/, emits one
    capture.stored, and NO model prose appears anywhere in the captures tree."""
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk")
    runlog = RunLog(run_id="r", ts=NOW, date=NOW[:10])
    faults: list = []
    _run_capture(_deps(layout, registry, _provider(), _cfg()), store, NOW, faults, runlog)

    assert runlog.sensors["capture"] == "ran"
    stored = registry.events_for_lead("disp-xlk", "capture.stored")
    assert len(stored) == 1
    payload = json.loads(stored[0]["payload"])
    assert payload["s3_prefix"] == capture_prefix("disp-xlk", NOW)
    assert payload["query_set"] and payload["result_counts"]

    blobs = list((tmp_path / "captures" / "disp-xlk").rglob("query_*.json"))
    assert blobs, "no capture blobs written"
    for b in blobs:
        obj = json.loads(b.read_text())
        assert obj["result_blocks"] and obj["fetched"]
        assert any("text" in f for f in obj["fetched"])
        assert "page text for" in json.dumps(obj["fetched"])
    # THE WALL: the model's prose must never be persisted, anywhere under captures/
    for f in (tmp_path / "captures").rglob("*"):
        if f.is_file():
            assert PROSE not in f.read_text(), f"model prose leaked into {f}"


def test_budget_breach_pauses_and_faults(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk")     # >= 2 templated queries
    runlog = RunLog(run_id="r", ts=NOW, date=NOW[:10])
    faults: list = []
    _run_capture(_deps(layout, registry, _provider(), _cfg(max_searches_per_week=1)),
                 store, NOW, faults, runlog)

    assert runlog.sensors["capture"] == "paused"        # loud, not a silent skip
    budget_faults = [f for f in faults if f.get("key") == "capture.budget:searches"]
    assert budget_faults and budget_faults[0]["category"] == "operational"
    # exactly one search was issued before the pause (the hard cap held)
    wk, _mo = period_keys(NOW)
    assert CaptureBudget(registry).count("week", wk) == 1


def test_budget_usd_cap_pauses(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk")
    runlog = RunLog(run_id="r", ts=NOW, date=NOW[:10])
    faults: list = []
    # unit_price 0.01, budget 0.02 -> pauses once the month's estimate reaches 2 searches
    _run_capture(_deps(layout, registry, _provider(), _cfg(monthly_budget_usd=0.02, unit_price_usd=0.01)),
                 store, NOW, faults, runlog)
    assert runlog.sensors["capture"] == "paused"
    assert any(f.get("key") == "capture.budget:usd" for f in faults)


def test_shadow_leads_never_capture(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-shadow", shadow=True)
    calls = {"n": 0}

    def counting_call(body):
        calls["n"] += 1
        return _fake_call(body)

    runlog = RunLog(run_id="r", ts=NOW, date=NOW[:10])
    faults: list = []
    _run_capture(_deps(layout, registry, _provider(call=counting_call), _cfg()), store, NOW, faults, runlog)

    assert calls["n"] == 0                              # shadow burn-in is never spent on
    assert runlog.sensors["capture"] == "skipped"
    assert not (tmp_path / "captures").exists()
    assert registry.events_for_lead("disp-shadow", "capture.stored") == []


def test_capture_disabled_when_unarmed(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk")
    runlog = RunLog(run_id="r", ts=NOW, date=NOW[:10])
    # no provider (no ANTHROPIC_API_KEY) -> disabled even with a budget set
    _run_capture(_deps(layout, registry, None, _cfg()), store, NOW, [], runlog)
    assert runlog.sensors["capture"] == "disabled"
    # budget null (shipped default) -> disabled even with a provider present
    runlog2 = RunLog(run_id="r2", ts=NOW, date=NOW[:10])
    _run_capture(_deps(layout, registry, _provider(), _cfg(monthly_budget_usd=None)), store, NOW, [], runlog2)
    assert runlog2.sensors["capture"] == "disabled"
    assert not (tmp_path / "captures").exists()


def test_recent_capture_is_skipped_by_weekly_gate(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk")
    # a capture 3 days ago -> the lead is NOT due this tick
    store.append({"ts": "2026-07-10T12:00:00Z", "lead": "disp-xlk", "type": "capture.stored",
                  "payload": {"query_set": ["q"], "s3_prefix": "captures/disp-xlk/x",
                              "result_counts": []}, "schema": 1})
    runlog = RunLog(run_id="r", ts=NOW, date=NOW[:10])
    _run_capture(_deps(layout, registry, _provider(), _cfg()), store, NOW, [], runlog)
    assert runlog.sensors["capture"] == "skipped"


def test_capture_meta_pulls_display_and_constituents(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk", display="XLK dispersion")
    state = fold(registry.events_for_lead("disp-xlk"))
    meta = _capture_meta(registry, "disp-xlk", state, 5)
    assert meta["display"] == "XLK dispersion"
    assert meta["constituents"] == ["Alpha Corp", "Beta Inc"]   # weight-desc


# --- backup carries the captures tree -----------------------------------------------------------

def test_backup_includes_captures(tmp_path):
    layout, registry, store = _store(tmp_path)
    _seed_lead(layout, registry, store, "disp-xlk")
    _run_capture(_deps(layout, registry, _provider(), _cfg()), store, NOW,
                 [], RunLog(run_id="r", ts=NOW, date=NOW[:10]))
    registry.close()
    blobs = list((tmp_path / "captures").rglob("query_*.json"))
    assert blobs, "precondition: a capture blob exists to back up"

    target = tmp_path / "hdd"
    target.mkdir()
    (target / DEFAULT_MARKER).write_text("blessed")    # the operator's per-drive marker
    report = backup_store(layout, [target])
    assert not report.failures
    # the un-backfillable capture blob landed on the target
    for b in blobs:
        rel = b.relative_to(tmp_path)
        assert (target / rel).is_file(), f"{rel} missing from backup target"


# --- the never-read wall (mirrors the firewall grep tests) --------------------------------------

def test_never_read_wall_only_capture_writer_touches_capture_blobs():
    """The write-only-substrate wall (build note §3f): NO module outside the capture writer locates a
    capture blob (`.captures_path(...)`), so nothing in v1 can read/interpret a capture — v2 earns read
    access by design, not by drift. Same shape as the portfolio-firewall grep tests: scan module source
    as text. `store/layout.py` DEFINES the accessor (`def captures_path`, not a `.captures_path(` call),
    and `store/backup.py` copies the whole tree by name without ever locating a blob — both pass."""
    import prospector
    pkg_dir = Path(prospector.__file__).parent
    writer = pkg_dir / "ingest" / "capture.py"
    scanned = 0
    for py in pkg_dir.rglob("*.py"):
        if py == writer:
            continue
        scanned += 1
        assert ".captures_path(" not in py.read_text(encoding="utf-8"), \
            f"{py.relative_to(pkg_dir)} locates a capture blob — the never-read wall forbids it"
    assert scanned > 0                                          # non-vacuous: modules were scanned
    assert ".captures_path(" in writer.read_text(encoding="utf-8")  # the writer IS allowed to


def test_capture_cli_command_tree_unchanged_no_run_now():
    """No-run-now CONTRACT (CLAUDE.md): M6 adds NO capture-trigger command — capture rides `pros run`
    only. The command tree must gain no capture/run-now surface."""
    from click.testing import CliRunner

    from prospector.cli.main import cli
    out = CliRunner().invoke(cli, ["--help"]).output.lower()
    assert "capture" not in out  # no `pros capture` / capture-trigger command
