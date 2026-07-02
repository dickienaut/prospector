"""Unknown-type contract (spec §5, test 3): anything unrecognized is counted and
raw-referenced in unknown_types, affects neither status nor verdict, and never crashes —
the day-one panel v2's writers plug into.

The strategy excludes types ending '.reverted': the fold deliberately treats any '.reverted'
suffix as a revert (spec §5 lead model), so those are recognized, not unknown."""

from __future__ import annotations

from datetime import datetime

from hypothesis import given, settings, strategies as st

from prospector.fold.fold import V1_TYPES, fold
from prospector.store.envelope import canonical_json

_json_scalars = (
    st.none() | st.booleans()
    | st.integers(min_value=-10**6, max_value=10**6)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=12))
json_objects = st.dictionaries(st.text(max_size=8), _json_scalars, max_size=4)

timestamps = st.datetimes(
    min_value=datetime(2020, 1, 1), max_value=datetime(2032, 1, 1),
).map(lambda dt: dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"))

unknown_type_st = st.text(min_size=1, max_size=24).filter(
    lambda t: t not in V1_TYPES and not t.endswith(".reverted"))

unknown_rows_st = st.lists(
    st.fixed_dictionaries({
        "event_id": st.uuids().map(lambda u: "u" + u.hex[:10]),
        "ts": timestamps,
        "type": unknown_type_st,
        "payload": json_objects | json_objects.map(canonical_json),
    }),
    min_size=1, max_size=8, unique_by=lambda r: r["event_id"])


def _row(event_id, ts, type_, payload):
    return {"event_id": event_id, "ts": ts, "type": type_,
            "payload": payload, "lead": "ld_u", "schema": 1}


_SPAWN = _row("b1", "2026-07-01T00:00:00Z", "lead.spawned",
              {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False})
_DEPART = _row("b2", "2026-07-02T00:00:00Z", "xcorr.departure", {"z": 2.9})
_REVERT = _row("b3", "2026-07-03T00:00:00Z", "xcorr.reverted", {"z": 0.7})
_VERDICT = _row("b4", "2026-07-04T00:00:00Z", "verdict",
                {"verdict": "watch", "note": "", "superseded_by": None})

# Every status/verdict corner unknowns must not disturb: fresh, active, reverted, adjudicated.
_BASES = [
    [],
    [_SPAWN],
    [_SPAWN, _DEPART],
    [_SPAWN, _DEPART, _REVERT],
    [_SPAWN, _DEPART, _VERDICT],
]


@st.composite
def base_and_unknowns(draw):
    base = draw(st.sampled_from(_BASES))
    unknowns = draw(unknown_rows_st)
    arrival = draw(st.permutations(list(base) + unknowns))
    return base, unknowns, arrival


@settings(deadline=None)
@given(base_and_unknowns())
def test_unknowns_counted_referenced_never_state(triple):
    base, unknowns, arrival = triple
    with_unknowns = fold(arrival)
    without = fold(list(base))
    for field in ("status", "shadow", "verdict", "verdict_history", "latest_z",
                  "spawned_at", "display", "spawner", "stress_departures"):
        assert with_unknowns[field] == without[field]
    assert with_unknowns["unknown_types"]["count"] == len(unknowns)
    expected = {(r["ts"], r["type"], r["event_id"]) for r in unknowns}
    got = {(i["ts"], i["type"], i["event_id"])
           for i in with_unknowns["unknown_types"]["items"]}
    assert got == expected
    assert with_unknowns["event_count"] == len(base) + len(unknowns)


def test_single_unknown_on_fresh_lead():
    state = fold([_row("u1", "2026-07-01T00:00:00Z", "llm.hypothesis", {"text": "?"})])
    assert state["status"] is None
    assert state["verdict"] == "none"
    assert state["unknown_types"] == {
        "count": 1,
        "items": [{"ts": "2026-07-01T00:00:00Z", "type": "llm.hypothesis",
                   "event_id": "u1"}]}
