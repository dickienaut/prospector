"""Fold determinism (spec §5, test 3): the same event set folds to the identical state in any
arrival order; duplicates by event_id dedupe; arbitrary JSON-object payloads and arbitrary
type strings never crash the fold. Plus the known-answer spawn → departure → tick → reverted
lifecycle, and a round-trip through the frozen registry (sqlite3.Row input)."""

from __future__ import annotations

from datetime import datetime

from hypothesis import given, settings, strategies as st

from prospector.fold.fold import V1_TYPES, fold, state_changed
from prospector.store.envelope import canonical_json

STATE_KEYS = {
    "lead", "display", "spawner", "status", "shadow", "verdict", "verdict_history",
    "spawned_at", "last_event", "event_count", "latest_z", "stress_departures",
    "capture_inventory", "corroborations", "unknown_types", "faults", "anomalies",
}

_json_scalars = (
    st.none() | st.booleans()
    | st.integers(min_value=-10**6, max_value=10**6)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=12))
_json_values = st.recursive(
    _json_scalars,
    lambda children: (st.lists(children, max_size=3)
                      | st.dictionaries(st.text(max_size=6), children, max_size=3)),
    max_leaves=8)
json_objects = st.dictionaries(st.text(max_size=8), _json_values, max_size=4)

timestamps = st.datetimes(
    min_value=datetime(2020, 1, 1), max_value=datetime(2032, 1, 1),
).map(lambda dt: dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"))

event_types = st.sampled_from(sorted(V1_TYPES)) | st.text(min_size=1, max_size=16)

# Both payload forms the fold contract admits: dict (fresh write), canonical-JSON text
# (registry row).
payloads = json_objects | json_objects.map(canonical_json)


def _rows(min_size=0):
    return st.lists(
        st.fixed_dictionaries(
            {"event_id": st.uuids().map(lambda u: u.hex[:12]),
             "ts": timestamps,
             "type": event_types,
             "payload": payloads},
            optional={"lead": st.sampled_from(["ld_prop", "_system"]),
                      "schema": st.just(1)}),
        min_size=min_size, max_size=10, unique_by=lambda r: r["event_id"])


@st.composite
def rows_and_permutation(draw):
    rows = draw(_rows())
    return rows, draw(st.permutations(rows))


@settings(deadline=None)
@given(rows_and_permutation())
def test_any_permutation_folds_identically(pair):
    rows, permuted = pair
    baseline = fold(rows)
    assert fold(permuted) == baseline
    assert baseline["event_count"] == len(rows)
    assert set(baseline) == STATE_KEYS


@st.composite
def rows_with_duplicates(draw):
    rows = draw(_rows(min_size=1))
    dupes = draw(st.lists(st.sampled_from(rows), min_size=1, max_size=4))
    return rows, draw(st.permutations(rows + dupes))


@settings(deadline=None)
@given(rows_with_duplicates())
def test_duplicates_by_event_id_dedupe(pair):
    rows, with_dupes = pair
    state = fold(with_dupes)
    assert state == fold(rows)
    assert state["event_count"] == len(rows)


def test_empty_fold_is_initial_state():
    state = fold([])
    assert set(state) == STATE_KEYS
    assert state["status"] is None
    assert state["shadow"] is False
    assert state["verdict"] == "none"
    assert state["event_count"] == 0
    assert state["last_event"] is None
    assert state["latest_z"] is None
    assert state_changed(None, state) == []


def _row(event_id, ts, type_, payload, lead="ld_ka"):
    return {"event_id": event_id, "ts": ts, "type": type_,
            "payload": payload, "lead": lead, "schema": 1}


_LIFECYCLE = [
    _row("e1", "2026-07-01T00:00:00Z", "lead.spawned",
         {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}),
    _row("e2", "2026-07-02T00:00:00Z", "xcorr.departure", {"z": 2.7}),
    _row("e3", "2026-07-09T00:00:00Z", "xcorr.tick", {"z": 3.1}),
    _row("e4", "2026-07-16T00:00:00Z", "xcorr.reverted", {"z": 0.8}),
]


def test_known_answer_spawn_tick_reverted():
    spawned = fold(_LIFECYCLE[:1])
    assert spawned["status"] == "active"
    assert spawned["spawner"] == "xcorr"
    assert spawned["display"] == "XLK×XLU"
    assert spawned["shadow"] is False
    assert spawned["spawned_at"] == "2026-07-01T00:00:00Z"
    assert state_changed(None, spawned) == ["status"]

    ticking = fold(_LIFECYCLE[:3])
    assert ticking["status"] == "active"
    assert ticking["latest_z"] == 3.1
    assert state_changed(spawned, ticking) == []

    reverted = fold(_LIFECYCLE)
    assert reverted["status"] == "reverted"
    assert reverted["latest_z"] == 3.1  # a revert records z but does not update latest_z
    assert reverted["event_count"] == 4
    assert reverted["last_event"] == {
        "ts": "2026-07-16T00:00:00Z", "type": "xcorr.reverted", "event_id": "e4"}
    assert reverted["lead"] == "ld_ka"
    assert reverted["verdict"] == "none"
    assert reverted["unknown_types"] == {"count": 0, "items": []}
    assert reverted["anomalies"] == []
    assert state_changed(ticking, reverted) == ["status"]


def test_departure_after_revert_reactivates():
    rows = _LIFECYCLE + [
        _row("e5", "2026-08-01T00:00:00Z", "xcorr.departure", {"z": 2.8})]
    state = fold(rows)
    assert state["status"] == "active"
    assert state["latest_z"] == 2.8


def test_corroborations_faults_and_captures_accumulate():
    rows = _LIFECYCLE[:2] + [
        _row("e5", "2026-07-03T00:00:00Z", "launch",
             {"series_id": "S000012345", "ticker": "TEKX"}),
        _row("e6", "2026-07-04T00:00:00Z", "rebalance", {"series_id": "S000012345"}),
        _row("e7", "2026-07-05T00:00:00Z", "mandate.changed", {"series_id": "S000012345"}),
        _row("e8", "2026-07-06T00:00:00Z", "capture.stored",
             {"query_set": ["q1"], "s3_prefix": "captures/ld_ka/x", "result_counts": [3]}),
        _row("e9", "2026-07-07T00:00:00Z", "fault",
             {"subsystem": "ingest", "message": "boom"}),
    ]
    state = fold(rows)
    assert [c["type"] for c in state["corroborations"]] == [
        "launch", "rebalance", "mandate.changed"]
    assert state["capture_inventory"] == [{
        "ts": "2026-07-06T00:00:00Z", "event_id": "e8", "query_set": ["q1"],
        "s3_prefix": "captures/ld_ka/x", "result_counts": [3]}]
    assert state["faults"] == [{
        "ts": "2026-07-07T00:00:00Z", "event_id": "e9",
        "subsystem": "ingest", "message": "boom"}]
    assert state["status"] == "active"  # none of the above are status changes


def test_fold_accepts_registry_rows(registry):
    for r in _LIFECYCLE:
        registry.insert_event(
            event_id=r["event_id"], ts=r["ts"], lead=r["lead"], type=r["type"],
            schema=r["schema"], payload_json=canonical_json(r["payload"]),
            sha256="0" * 64, file_path=f"events/ld_ka/{r['event_id']}.json",
            ingested_at="2026-07-16T00:00:00Z")
    assert fold(registry.events_for_lead("ld_ka")) == fold(_LIFECYCLE)
