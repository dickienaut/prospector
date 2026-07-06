"""The divergence guard in write_snapshot (spec §5). First-write-wins on a (lead, ts) snapshot is
correct only while events are monotonic and the fold is deterministic. A rewrite carrying a
DIFFERENT state (beyond the reason field) means one of those invariants broke — a backdated event
or a nondeterministic fold — so rather than silently keep the old bytes, we make it loud: raise
(pure caller), or emit a `fault` on _system via the injected sink (the runner's path).

Audit = detection: the old bytes are always kept so the record stays consistent; the divergence is
surfaced, never masked."""

import json

import pytest

from prospector.fold.snapshots import SnapshotDivergenceError, write_snapshot
from prospector.primitives.atomic import sha256_file
from prospector.store.envelope import validate
from prospector.store.layout import ts_compact

TS = "2026-07-14T13:00:00Z"
STATE = {"status": "active", "event_count": 3, "latest_z": 2.7}


# -- S2: ts_compact is sub-second-lossless, so same-second snapshots don't collide ----------------

def test_ts_compact_is_lossless_across_subsecond_instants():
    # Whole-second form is unchanged (backward-compatible); sub-second instants are distinguished.
    assert ts_compact("2026-07-14T13:00:00Z") == "20260714T130000Z"
    a = ts_compact("2026-07-14T13:00:00.100000Z")
    b = ts_compact("2026-07-14T13:00:00.900000Z")
    assert a == "20260714T130000_100000Z" and a != b


def test_two_subsecond_snapshots_same_second_do_not_collide_or_diverge(layout, registry):
    # S2 end-to-end: the runner's reactive policy can snapshot one lead twice in the SAME wall-clock
    # second on a state change. With a lossless compact form the two DIFFERENT states land on DISTINCT
    # files — no SnapshotDivergenceError abort. (Pre-fix both mapped to …130000Z and the second raised.)
    first = write_snapshot(layout, registry, "lead_x", {"status": "active"}, "state_change",
                           "2026-07-14T13:00:00.100000Z")
    second = write_snapshot(layout, registry, "lead_x", {"status": "reverted"}, "state_change",
                            "2026-07-14T13:00:00.900000Z")
    assert first != second and first.exists() and second.exists()


# -- identical state: first-write-wins, no fault, no raise ---------------------

def test_rewrite_with_identical_state_is_fine_first_write_wins(layout, registry):
    first = write_snapshot(layout, registry, "lead_x", STATE, "state_change", TS)
    sha_before = sha256_file(first)

    faults = []
    # Same state, DIFFERENT reason — allowed. No fault, no raise.
    second = write_snapshot(layout, registry, "lead_x", dict(STATE), "active_daily", TS,
                            fault_sink=faults.append)

    assert second == first
    assert faults == []
    # File kept as the first write (its reason survives), and the indexed sha matches the bytes.
    assert first.exists()
    assert json.loads(first.read_text(encoding="utf-8"))["reason"] == "state_change"
    assert sha256_file(first) == sha_before
    assert registry.latest_snapshot("lead_x")["sha256"] == sha_before


# -- different state, NO sink: raises -----------------------------------------

def test_rewrite_with_different_state_and_no_sink_raises(layout, registry):
    first = write_snapshot(layout, registry, "lead_x", STATE, "state_change", TS)
    before = first.read_bytes()

    diverged = {"status": "reverted", "event_count": 9}
    with pytest.raises(SnapshotDivergenceError):
        write_snapshot(layout, registry, "lead_x", diverged, "state_change", TS)

    # Old bytes untouched (first-write-wins is preserved even as we surface the break).
    assert first.read_bytes() == before


# -- different state, WITH sink: no raise, one valid fault envelope ------------

def test_rewrite_with_different_state_and_sink_emits_one_fault(layout, registry):
    first = write_snapshot(layout, registry, "lead_x", STATE, "state_change", TS)
    before = first.read_bytes()

    faults = []
    diverged = {"status": "reverted", "event_count": 9}
    # WITH a sink: does NOT raise; the divergence reaches the fault surface instead.
    result = write_snapshot(layout, registry, "lead_x", diverged, "state_change", TS,
                            fault_sink=faults.append)

    assert result == first
    # Sink called exactly once.
    assert len(faults) == 1

    # The emitted dict is a valid five-field envelope: a `fault` on `_system` whose payload names
    # the 'snapshot' subsystem and the diverged lead.
    envelope = validate(faults[0])  # raises EnvelopeError if the shape is wrong
    assert envelope.type == "fault"
    assert envelope.lead == "_system"
    assert envelope.ts == TS
    assert envelope.payload["subsystem"] == "snapshot"
    assert envelope.payload["lead"] == "lead_x"
    assert "message" in envelope.payload

    # The old file bytes are unchanged — keeping the record consistent (audit = detection).
    assert first.read_bytes() == before
