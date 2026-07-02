"""EventStore: atomic blob + index row per append, append-only surface, malformed events never
reach the record (spec §5/§7, CONTRACT)."""

import dataclasses
import json
from pathlib import Path

import pytest

from prospector.primitives.atomic import sha256_file
from prospector.store.envelope import Envelope, EnvelopeError, validate
from prospector.store.event_store import EventStore, WrittenEvent, envelope_from_row

FIXED_NOW = "2026-07-02T09:00:00Z"


def make_event(**over):
    e = {"ts": "2026-07-14T13:00:00Z", "lead": "lead_abc123", "type": "xcorr.tick",
         "payload": {"z": 3.2, "pair": ["S000001", "S000002"], "note": "×"}, "schema": 1}
    e.update(over)
    return e


@pytest.fixture
def store(layout, registry):
    return EventStore(layout, registry, clock=lambda: FIXED_NOW)


# -- append: file + row -----------------------------------------------------

def test_append_writes_file_at_layout_path(store, layout, store_root):
    raw = make_event()
    w = store.append(raw)
    assert isinstance(w, WrittenEvent)
    assert not Path(w.file_path).is_absolute()
    abs_path = store_root / w.file_path
    assert abs_path == layout.event_path(raw["lead"], raw["ts"], raw["type"], w.event_id)
    assert abs_path.is_file()
    assert json.loads(abs_path.read_text(encoding="utf-8")) == raw  # the five-field dict, exactly
    assert w.sha256 == sha256_file(abs_path)


def test_append_registry_row_matches_file(store, registry, store_root):
    raw = make_event()
    w = store.append(raw)
    (row,) = registry.events_for_lead(raw["lead"])
    assert row["event_id"] == w.event_id
    assert row["ts"] == raw["ts"]
    assert row["type"] == raw["type"]
    assert row["schema"] == raw["schema"]
    assert json.loads(row["payload"]) == raw["payload"]
    assert row["sha256"] == w.sha256 == sha256_file(store_root / row["file_path"])
    assert row["file_path"] == w.file_path
    assert row["ingested_at"] == FIXED_NOW
    assert envelope_from_row(row) == w.envelope


def test_append_accepts_envelope_instance(store):
    env = validate(make_event())
    w = store.append(env)
    assert w.envelope == env
    assert store.read_lead(env.lead) == [env]


def test_written_event_is_frozen(store):
    w = store.append(make_event())
    with pytest.raises(dataclasses.FrozenInstanceError):
        w.sha256 = "0" * 64


# -- idempotent re-ingest ------------------------------------------------------

def test_reinserting_same_event_id_is_idempotent(store, registry):
    w = store.append(make_event())
    (row,) = registry.events_for_lead("lead_abc123")
    inserted = registry.insert_event(
        event_id=w.event_id, ts=row["ts"], lead=row["lead"], type=row["type"],
        schema=row["schema"], payload_json=row["payload"], sha256=row["sha256"],
        file_path=row["file_path"], ingested_at="2026-07-03T00:00:00Z")
    assert inserted is False
    assert registry.event_count() == 1
    (row_after,) = registry.events_for_lead("lead_abc123")
    assert row_after["ingested_at"] == FIXED_NOW  # first write wins; re-ingest changed nothing


# -- reads --------------------------------------------------------------------

def test_read_lead_orders_and_filters(store):
    store.append(make_event(ts="2026-07-14T13:00:02Z", type="xcorr.tick"))
    store.append(make_event(ts="2026-07-14T13:00:00Z", type="lead.spawned"))
    store.append(make_event(ts="2026-07-14T13:00:01Z", type="xcorr.tick"))
    events = store.read_lead("lead_abc123")
    assert [e.ts for e in events] == ["2026-07-14T13:00:00Z", "2026-07-14T13:00:01Z",
                                      "2026-07-14T13:00:02Z"]
    assert all(isinstance(e, Envelope) for e in events)
    ticks = store.read_lead("lead_abc123", type="xcorr.tick")
    assert [e.type for e in ticks] == ["xcorr.tick", "xcorr.tick"]


def test_read_system(store):
    store.append(make_event(lead="_system", type="config.changed", payload={"diff": "x"}))
    store.append(make_event())
    events = store.read_system()
    assert [e.lead for e in events] == ["_system"]
    assert store.read_system(type="config.changed")[0].payload == {"diff": "x"}
    assert store.read_system(type="fault") == []


# -- leftover tmp files are invisible -------------------------------------------

def test_leftover_tmp_file_ignored(store, layout):
    w = store.append(make_event())
    lead_dir = layout.events_root() / "lead_abc123"
    # A crashed writer's leftover, named exactly as atomic.py names them.
    tmp = lead_dir / ".20260714T130000Z_xcorr.tick_deadbeef.json.ab12cd34.tmp"
    tmp.write_text("{ torn write", encoding="utf-8")

    # Reads (registry-backed) never see it.
    assert [e.to_dict() for e in store.read_lead("lead_abc123")] == [w.envelope.to_dict()]

    # A reindex-style scan of events/ must ignore *.tmp (atomic.py contract): everything
    # it picks up parses as a valid envelope.
    scanned = [p for p in layout.events_root().rglob("*")
               if p.is_file() and not p.name.endswith(".tmp")]
    assert scanned == [layout.events_root() / Path(w.file_path).relative_to("events")]
    for p in scanned:
        validate(json.loads(p.read_text(encoding="utf-8")))


# -- append-only by construction -------------------------------------------------

def test_no_mutation_surface(store):
    forbidden = ("update", "delete", "remove")
    exposed = [n for n in dir(store) if any(w in n.lower() for w in forbidden)]
    assert exposed == [], f"EventStore must not expose mutation methods: {exposed}"


# -- rejection writes NOTHING ------------------------------------------------------

@pytest.mark.parametrize("mangle", [
    lambda e: e.update(note="sixth field"),
    lambda e: e.pop("payload"),
    lambda e: e.update(ts="2026-07-14T13:00:00"),        # naive ts
    lambda e: e.update(lead="a/b"),
    lambda e: e.update(payload=[1, 2]),
    lambda e: e.update(schema=0),
])
def test_append_rejects_malformed_and_writes_nothing(store, layout, registry, mangle):
    bad = make_event()
    mangle(bad)
    with pytest.raises(EnvelopeError):
        store.append(bad)
    assert not layout.events_root().exists()  # no file — not even a directory
    assert registry.event_count() == 0        # no row
