"""Verdict supersession (spec §5, CONTRACT, test 3): verdicts are append-only; a changed mind
is a new verdict event linking the one it replaces via `superseded_by`. The current verdict
is the chain head — the verdict no other verdict references. Broken chains (dangling pointer,
fork) resolve deterministically to the latest (ts, event_id) head with an anomaly recorded,
never a crash; verdict_history preserves every link regardless."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

from prospector.fold.fold import fold

verdict_values = st.sampled_from(["yes", "no", "watch"])

_T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _ts(i):
    return (_T0 + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verdict_row(event_id, ts, verdict, superseded_by):
    return {"event_id": event_id, "ts": ts, "type": "verdict", "lead": "ld_v",
            "payload": {"verdict": verdict, "note": f"note for {event_id}",
                        "superseded_by": superseded_by},
            "schema": 1}


@st.composite
def valid_chains(draw, min_links=1, max_links=8):
    n = draw(st.integers(min_links, max_links))
    rows, prev = [], None
    for i in range(n):
        event_id = f"v{i:03d}"
        rows.append(_verdict_row(event_id, _ts(i), draw(verdict_values), prev))
        prev = event_id
    return rows


@st.composite
def chain_and_arrival(draw):
    rows = draw(valid_chains())
    return rows, draw(st.permutations(rows))


@settings(deadline=None)
@given(chain_and_arrival())
def test_valid_chain_head_is_last_link_any_arrival(pair):
    rows, arrival = pair
    state = fold(arrival)
    assert state["verdict"] == rows[-1]["payload"]["verdict"]
    assert [v["event_id"] for v in state["verdict_history"]] == [
        r["event_id"] for r in rows]
    assert [v["verdict"] for v in state["verdict_history"]] == [
        r["payload"]["verdict"] for r in rows]
    assert state["anomalies"] == []


@st.composite
def dangling_chain_and_arrival(draw):
    rows = draw(valid_chains())
    broken = draw(st.integers(0, len(rows) - 1))
    rows[broken]["payload"]["superseded_by"] = "ghost_" + draw(
        st.text(alphabet="abcdef", min_size=1, max_size=6))
    return rows, draw(st.permutations(rows))


@settings(deadline=None)
@given(dangling_chain_and_arrival())
def test_dangling_pointer_records_anomaly_and_latest_wins(pair):
    rows, arrival = pair
    state = fold(arrival)
    kinds = [a["kind"] for a in state["anomalies"]]
    assert "verdict_dangling" in kinds
    # Deterministic latest-wins: the last link by (ts, event_id) is always a head here.
    assert state["verdict"] == rows[-1]["payload"]["verdict"]
    assert len(state["verdict_history"]) == len(rows)


@st.composite
def forked_chain_and_arrival(draw):
    rows = draw(valid_chains(min_links=2))
    # Point the fork at an already-superseded link, so two verdicts claim the same parent.
    target = rows[draw(st.integers(0, len(rows) - 2))]["event_id"]
    fork = _verdict_row("vfork", _ts(len(rows)), draw(verdict_values), target)
    return rows, fork, draw(st.permutations(rows + [fork]))


@settings(deadline=None)
@given(forked_chain_and_arrival())
def test_fork_records_anomaly_and_latest_wins(triple):
    rows, fork, arrival = triple
    state = fold(arrival)
    forks = [a for a in state["anomalies"] if a["kind"] == "verdict_fork"]
    assert len(forks) == 1
    assert forks[0]["resolved_to"] == "vfork"  # latest (ts, event_id) of the two heads
    assert rows[-1]["event_id"] in forks[0]["heads"]
    assert state["verdict"] == fork["payload"]["verdict"]
    assert len(state["verdict_history"]) == len(rows) + 1


def test_fork_tie_on_ts_breaks_on_event_id():
    root = _verdict_row("v000", _ts(0), "watch", None)
    head_a = _verdict_row("va", _ts(1), "no", "v000")
    head_b = _verdict_row("vb", _ts(1), "yes", "v000")  # same ts; max event_id wins
    state = fold([head_b, root, head_a])
    assert state["verdict"] == "yes"
    forks = [a for a in state["anomalies"] if a["kind"] == "verdict_fork"]
    assert forks[0]["resolved_to"] == "vb"
    assert forks[0]["heads"] == ["va", "vb"]


def test_no_verdicts_means_verdict_none():
    assert fold([])["verdict"] == "none"
    assert fold([])["verdict_history"] == []


def test_cycle_resolves_to_latest_with_anomaly():
    a = _verdict_row("va", _ts(0), "no", "vb")
    b = _verdict_row("vb", _ts(1), "yes", "va")
    state = fold([a, b])
    assert state["verdict"] == "yes"  # latest (ts, event_id)
    assert [x["kind"] for x in state["anomalies"]] == ["verdict_cycle"]
    assert len(state["verdict_history"]) == 2
