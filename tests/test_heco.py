"""Spec §10 test 1 — the HECO rule end-to-end. Ticker HECO resolves to the State Street Galaxy
fund's series id via (fixture-served) EDGAR and lands in the registry keyed on it;
`category_draft` — etfdb's stale ESG label from the ticker's previous owner — is stored
verbatim but never used for identity or baselines: the identity modules never branch on it,
and the lead-id/baseline path never mentions it at all."""

import inspect
import json
import re
from pathlib import Path

import pytest

import prospector
import prospector.identity.resolution as resolution_module
import prospector.store.fund_registry as fund_registry_module
from prospector.identity.resolution import ResolutionMachine
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError, Resolution, \
    resolve_ticker
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundEntry, FundRegistry

FIXTURES = Path(__file__).parent / "fixtures"
EDGAR = FIXTURES / "edgar"
HECO = json.loads((FIXTURES / "heco.json").read_text(encoding="utf-8"))
EXPECTED = HECO["expected_entry"]

FIXED_NOW = "2026-07-02T00:00:00Z"
UA = "Prospector-tests/1.0 (lyle.e.dickie@gmail.com)"

_FIXTURE_BY_URL = {
    MF_TICKERS_URL: "company_tickers_mf.json",
    "https://data.sec.gov/submissions/CIK0001516212.json": "heco_submissions.json",
    "https://data.sec.gov/submissions/CIK0001064641.json": "sectors_submissions.json",
}


def fixture_fetch(url, headers):
    if url not in _FIXTURE_BY_URL:
        raise EdgarError(f"no fixture for {url}", status=404)
    return (EDGAR / _FIXTURE_BY_URL[url]).read_bytes()


@pytest.fixture
def client():
    """Fixture-backed client with a fake monotonic clock — no real waiting, no sockets."""
    mono = {"t": 0.0}

    def sleep(seconds):
        mono["t"] += seconds

    return EdgarClient(UA, fetch=fixture_fetch, clock=lambda: mono["t"], sleep=sleep)


@pytest.fixture
def event_store(layout, registry):
    return EventStore(layout, registry, clock=lambda: FIXED_NOW)


@pytest.fixture
def funds(layout, registry, event_store):
    return FundRegistry(layout, registry, event_store, clock=lambda: FIXED_NOW)


@pytest.fixture
def machine(registry, event_store, funds, client):
    return ResolutionMachine(registry, event_store, funds, client,
                             clock=lambda: FIXED_NOW)


# -- HECO resolves and lands keyed on its series id (spec test 1) -----------------------

def test_heco_resolution_stored_entry_matches_fixture(machine, funds, client):
    resolution = resolve_ticker("HECO", client)
    assert isinstance(resolution, Resolution)
    entry = machine.build_entry(resolution,
                                category_draft=HECO["etfdb_stale_category"])
    funds.upsert(entry)

    stored = funds.get(EXPECTED["series_id"])
    assert stored is not None  # keyed on the series id, not the ticker
    assert stored.series_id == EXPECTED["series_id"]
    assert stored.class_ids == EXPECTED["class_ids"]
    assert stored.cik == EXPECTED["cik"]
    assert stored.ticker_current == EXPECTED["ticker_current"] == "HECO"
    assert stored.issuer == EXPECTED["issuer"]
    assert stored.prospectus_accession == EXPECTED["prospectus_accession"]
    assert stored.holdings_source == EXPECTED["holdings_source"] == "issuer_daily"
    # The stale ESG label from the ticker's previous owner is stored VERBATIM — recorded
    # context, steering only, decides nothing.
    assert stored.category_draft == HECO["etfdb_stale_category"] == "Environmentally Responsible"
    # The prospectus parse that fills concentration_industries is v-later; empty at this stage
    # (the fixture's expected list documents where it will come from, not what we store now).
    assert stored.concentration_industries == []


def test_entry_builder_timestamps(machine, client):
    resolution = resolve_ticker("HECO", client)
    fresh = machine.build_entry(resolution)
    assert fresh.first_seen == fresh.verified_at == FIXED_NOW
    assert fresh.category_draft is None
    # A two-phase launch supplies the ORIGINAL detected_at (§4c): first_seen keeps it.
    detected = "2026-06-30T13:00:00Z"
    entry = machine.build_entry(resolution, detected_at=detected)
    assert entry.first_seen == detected
    assert entry.verified_at == FIXED_NOW


# -- category_draft is steering only: nothing branches on it, spec test 1 ----------------

_BRANCH_FRAGMENTS = ("category_draft ==", "== category_draft", "category_draft !=",
                     "!= category_draft", "category_draft in ", "in category_draft",
                     "category_draft is ", "is category_draft", "not category_draft")


def _assert_never_branched_on(source: str):
    for line in source.splitlines():
        if "category_draft" not in line:
            continue
        stripped = line.strip()
        assert not stripped.startswith(("if ", "elif ", "while ", "assert ", "return ")), line
        for fragment in _BRANCH_FRAGMENTS:
            assert fragment not in line, line


def test_resolution_module_never_branches_on_category_draft():
    src = inspect.getsource(resolution_module)
    assert "category_draft" in src  # it rides through the builder and the launch payload...
    _assert_never_branched_on(src)  # ...but never steers control flow
    # And it is never read back off an entry, row, or payload in this module.
    assert ".category_draft" not in src
    assert not re.search(r"\[.category_draft.\]", src)


def test_fund_registry_confines_category_draft_to_the_entry_container():
    module_src = inspect.getsource(fund_registry_module)
    entry_src = inspect.getsource(FundEntry)
    assert "category_draft" in entry_src  # the container carries it...
    assert "category_draft" not in module_src.replace(entry_src, "")  # ...nothing else reads it
    _assert_never_branched_on(module_src)


def test_lead_and_baseline_paths_never_mention_category_draft():
    """Nothing downstream — no lead, no baseline — may anchor to it (spec §2): the store and
    fold packages never even mention the label, except the FundEntry container itself."""
    pkg = Path(prospector.__file__).parent
    store_files = [p for p in (pkg / "store").glob("*.py") if p.name != "fund_registry.py"]
    fold_files = list((pkg / "fold").glob("*.py"))
    assert store_files and fold_files  # the assertion below is not vacuous
    for path in store_files + fold_files:
        assert "category_draft" not in path.read_text(encoding="utf-8"), path
