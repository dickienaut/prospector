"""§4d mandate-diff on cadence + the §9c frozen-prior invariant (SUBTLE BIT #2).

The gate here is the §9c invariant, proved the way it can actually go wrong: the runner must source the
mandate diff's PRIOR from the last FROZEN prospectus blob, NEVER the registry `prospectus_accession`
field — because an identity pass earlier in the same run may have already advanced that field to the new
filing. So the invariant test seeds exactly that hazard — registry field already == the NEW accession,
the real prior held only as a frozen blob — and proves the diff still fires against the frozen prior
(reading the registry field would diff the new filing against itself and miss the change).

Plus: baseline on first sight (freeze, no event), and a per-fund fetch failure is a soft fault. Offline:
the EdgarClient fetch is injected over the recorded 485BPOS fixture + controlled deltas.
"""

import json
from pathlib import Path

from prospector.config import load_config
from prospector.ingest.edgar import EdgarClient, EdgarError
from prospector.ingest.prices import PriceIngest
from prospector.ingest.prospectus import ProspectusIngest
from prospector.primitives.atomic import write_atomic
from prospector.runner.deps import RunnerDeps
from prospector.runner.notify import NullNotifier
from prospector.runner.runlog import RunLog
from prospector.runner.runner import _run_mandate
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundEntry, FundRegistry

CONFIG = Path("config") / "prospector.yaml"
FIX = Path(__file__).parent / "fixtures" / "prospectus"
BASE = (FIX / "485bpos_base.html").read_bytes()
# A substantive strategy rewrite off the base (method + threshold + sector) — mirrors test_mandate_sensor.
SUBSTANTIVE = (BASE.replace(b"employs a replication strategy",
                            b"employs a representative sampling strategy")
                   .replace(b"at least 95% of its total", b"at least 80% of its total")
                   .replace(b"information technology sector", b"health care sector"))

NOW = "2026-07-06T22:30:00Z"
CIK = 1516212
XLK_SID = "S000006415"
A = "0001193125-25-280452"   # the PRIOR prospectus (held frozen)
B = "0001193125-26-291833"   # the NEW prospectus
DOCB = "docB.htm"
SUBS_URL = f"https://data.sec.gov/submissions/CIK{CIK:010d}.json"
DOCB_URL = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{B.replace('-', '')}/{DOCB}"


def _entry(prospectus_accession):
    return FundEntry(series_id=XLK_SID, class_ids=[], cik=CIK, ticker_current="XLK",
                     name="Tech Select", issuer="Select Sector SPDR Trust", category_draft=None,
                     concentration_industries=[], prospectus_accession=prospectus_accession,
                     holdings_source="issuer_daily", first_seen=NOW, verified_at=NOW)


def _subs_AB():
    # `recent` is newest-first: B (2026) then A (2025). latest_prospectus -> B; history -> [B, A].
    return {"name": "Select Sector SPDR Trust", "filings": {"recent": {
        "form": ["485BPOS", "485BPOS"], "accessionNumber": [B, A],
        "primaryDocument": [DOCB, "docA.htm"], "filingDate": ["2026-05-01", "2025-05-01"]}}}


def _prefreeze(layout, accession, body):
    """Freeze a prospectus blob as a prior run's baseline would have (the §9c prior lives here)."""
    write_atomic(layout.prospectus_path(XLK_SID, accession, "index.html"), body)


def _deps(layout, registry, event_store, fetch):
    cfg, cfg_hash = load_config(CONFIG)
    clock = {"t": 0.0}
    edgar = EdgarClient("Test/1.0 (test@example.com)", fetch=fetch, clock=lambda: clock["t"],
                        sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                        persist=lambda name, body: write_atomic(layout.edgar_path(NOW[:10], name), body))
    return RunnerDeps(layout=layout, registry=registry, event_store=event_store, edgar_client=edgar,
                      price_ingest=PriceIngest(layout, fetch=lambda url, headers: b"",
                                               sleep=lambda _s: None),  # inert: _run_mandate never builds the panel
                      notifier=NullNotifier(), cfg=cfg, cfg_hash=cfg_hash, now=NOW, run_id="r",
                      monotonic=lambda: 0.0)


# === §9c invariant: the diff uses the FROZEN prior, never the advanced registry field ===============

def test_mandate_diff_uses_the_frozen_prior_not_the_advanced_registry_field(layout, registry):
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    # THE HAZARD: the registry field is ALREADY advanced to B (as an intra-run identity pass leaves it).
    funds.upsert(_entry(prospectus_accession=B))
    _prefreeze(layout, A, BASE)  # the true prior (A) is held only as a frozen blob

    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs_AB()).encode()
        if url == DOCB_URL:
            return SUBSTANTIVE
        raise EdgarError(f"no fixture for {url}", status=404)

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_mandate(deps, event_store, NOW, faults, runlog, funds)

    # The diff fired against the FROZEN A (not B, the registry field): reading the field would have
    # diffed B vs B -> no change -> no event. A single mandate.changed with prior A proves the invariant.
    changed = event_store.read_system("mandate.changed")
    assert len(changed) == 1
    assert changed[0].payload["prior_accession"] == A       # the frozen prior — NOT B, the advanced field
    assert changed[0].payload["current_accession"] == B
    assert changed[0].payload["summary"]
    assert faults == [] and runlog.sensors["mandate"] == "ran"


# === baseline on first sight: freeze the current, emit nothing =====================================

def test_mandate_first_sight_freezes_a_baseline_and_emits_nothing(layout, registry):
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    funds.upsert(_entry(prospectus_accession=B))
    # No prior frozen (A is not on file) -> mandate.scan baselines B (freezes it), emits nothing.

    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs_AB()).encode()
        if url == DOCB_URL:
            return BASE
        raise EdgarError(f"no fixture for {url}", status=404)

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_mandate(deps, event_store, NOW, faults, runlog, funds)

    assert event_store.read_system("mandate.changed") == []
    assert ProspectusIngest(layout, deps.edgar_client).has_frozen(XLK_SID, B)  # current frozen as baseline
    assert faults == []


# === per-fund failure is a soft fault; the pass goes on (§9g) =======================================

def test_mandate_per_fund_failure_is_a_soft_fault(layout, registry):
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    funds.upsert(_entry(prospectus_accession=B))

    def fetch(url, headers):
        raise EdgarError("edgar down", status=500)  # submissions fetch fails for this fund

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_mandate(deps, event_store, NOW, faults, runlog, funds)

    assert any(f["subsystem"] == "mandate" for f in faults)
    assert event_store.read_system("mandate.changed") == []
