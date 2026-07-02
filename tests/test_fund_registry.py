"""FundRegistry: the HECO rule's enforcement point — series-id-keyed writes, bare tickers
rejected before anything lands, tickers display-only, category_draft steering-only
(spec §2 CONTRACT; §10 test 1)."""

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

import prospector.store.fund_registry as fund_registry_module
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundEntry, FundRegistry, IdentityError

FIXTURES = Path(__file__).parent / "fixtures"
HECO = json.loads((FIXTURES / "heco.json").read_text(encoding="utf-8"))["expected_entry"]


def make_entry(**over):
    d = dict(HECO)
    d.update(over)
    return FundEntry(**d)


@pytest.fixture
def clock():
    # Monotonic fixed clock: deterministic event order without wall time.
    seconds = iter(range(60))
    return lambda: f"2026-07-02T09:00:{next(seconds):02d}Z"


@pytest.fixture
def event_store(layout, registry, clock):
    return EventStore(layout, registry, clock=clock)


@pytest.fixture
def funds(layout, registry, event_store, clock):
    return FundRegistry(layout, registry, event_store, clock=clock)


# -- rejection writes NOTHING (the HECO rule, spec §2 CONTRACT) -----------------

@pytest.mark.parametrize("bad", [
    {"series_id": "HECO"},              # the eponymous case: a bare ticker
    {"series_id": "S12"},               # truncated series id
    {"series_id": ""},
    {"series_id": None},
    {"class_ids": ["HECO"]},            # a ticker where a class id belongs
    {"class_ids": "C000253658"},        # bare string, not a list
])
def test_malformed_identity_rejected_and_nothing_written(funds, layout, registry, bad):
    with pytest.raises(IdentityError):
        funds.upsert(make_entry(**bad))
    assert not (layout.root / "registry").exists()  # no object file — not even the directory
    assert registry.conn.execute("SELECT COUNT(*) FROM funds").fetchone()[0] == 0  # no row
    assert registry.event_count() == 0                                            # no event


# -- valid upsert: file + row + registry.updated --------------------------------

def test_upsert_writes_versioned_object_at_fund_path(funds, layout):
    entry = make_entry()
    funds.upsert(entry)
    path = layout.fund_path(entry.series_id)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == dataclasses.asdict(entry)


def test_upsert_row_present_keyed_on_series_id(funds, registry):
    funds.upsert(make_entry())
    (row,) = registry.conn.execute("SELECT * FROM funds").fetchall()
    assert row["series_id"] == HECO["series_id"]
    assert row["ticker_current"] == "HECO"
    assert json.loads(row["entry_json"]) == HECO


def test_upsert_emits_registry_updated_created(funds, event_store):
    funds.upsert(make_entry())
    (event,) = event_store.read_system(type="registry.updated")
    assert event.payload == {"series_id": HECO["series_id"], "ticker": "HECO",
                             "change": "created", "fields_changed": []}


# -- second upsert: diffed change summary + round-trip ---------------------------

def test_second_upsert_diffs_fields_changed(funds, event_store):
    funds.upsert(make_entry())
    funds.upsert(make_entry(verified_at="2026-07-03T00:00:00Z"))
    created, updated = event_store.read_system(type="registry.updated")
    assert created.payload["change"] == "created"
    assert updated.payload["change"] == "updated"
    assert updated.payload["fields_changed"] == ["verified_at"]


def test_entry_round_trips_via_get(funds):
    funds.upsert(make_entry())
    second = make_entry(verified_at="2026-07-03T00:00:00Z")
    funds.upsert(second)
    got = funds.get(HECO["series_id"])
    assert got == second
    assert got.class_ids == ["C000253658"]  # list survives serialization
    assert got.category_draft == "Environmentally Responsible"  # stored, never trusted
    assert funds.get("S000000000") is None
    assert funds.all_funds() == [second]


# -- tickers are display-only -----------------------------------------------------

def test_by_ticker_display_lookup(funds):
    entry = make_entry()
    funds.upsert(entry)
    assert funds.by_ticker("HECO") == entry
    assert funds.by_ticker("ZZZQ") is None


def test_ticker_never_keys(funds, registry, layout):
    funds.upsert(make_entry())
    # The funds PK is series_id — the ticker column carries no keying role.
    pk_cols = [r["name"] for r in registry.conn.execute("PRAGMA table_info(funds)")
               if r["pk"]]
    assert pk_cols == ["series_id"]
    # The versioned object is named by series id, not ticker.
    assert layout.fund_path(HECO["series_id"]).name == f"{HECO['series_id']}.json"
    assert not (layout.root / "registry" / "funds" / "HECO.json").exists()


# -- category_draft is steering only (spec §10 test 1) ------------------------------

def test_category_draft_confined_to_the_entry_container():
    module_src = inspect.getsource(fund_registry_module)
    entry_src = inspect.getsource(FundEntry)
    assert "category_draft" in entry_src  # the container carries it...
    # ...and NOTHING else does: no lookup, validation, diff, or DDL logic reads it.
    assert "category_draft" not in module_src.replace(entry_src, "")
    assert "category_draft" not in inspect.getsource(FundRegistry)
