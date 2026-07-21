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
from prospector.ingest.holdings import HoldingsIngest
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
STICKER = (FIX / "497_supplement_sticker.html").read_bytes()  # a real 497 "Supplement dated…" sticker
# A substantive strategy rewrite off the base (method + threshold + sector) — mirrors test_mandate_sensor.
SUBSTANTIVE = (BASE.replace(b"employs a replication strategy",
                            b"employs a representative sampling strategy")
                   .replace(b"at least 95% of its total", b"at least 80% of its total")
                   .replace(b"information technology sector", b"health care sector"))

NOW = "2026-07-06T22:30:00Z"
CIK = 1516212
XLK_SID = "S000006415"
A = "0001193125-25-280452"   # the PRIOR annual prospectus (held frozen)
S = "0001193125-26-285000"   # an intervening 497 SUPPLEMENT (sticker), newer than A, older than B
B = "0001193125-26-291833"   # the NEW annual prospectus
DOCB = "docB.htm"
W = "0001193125-26-290000"   # a WRONG-FUND filing frozen under this series by B1 over-attribution
SUBS_URL = f"https://data.sec.gov/submissions/CIK{CIK:010d}.json"
DOCB_URL = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{B.replace('-', '')}/{DOCB}"


def _hdr_url(acc):
    return f"https://www.sec.gov/Archives/edgar/data/{CIK}/{acc.replace('-', '')}/{acc}.txt"


def _hdr_bytes(*series_ids):
    """A synthetic SGML submission header covering the given series (declared-synthetic; the real header
    shapes are exercised in test_mandate_sensor with recorded fixtures)."""
    b = b"<SEC-HEADER>\n<SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    for sid in series_ids:
        b += b"<SERIES>\n<SERIES-ID>" + sid.encode() + b"\n"
    return b + b"</SERIES-AND-CLASSES-CONTRACTS-DATA>\n</SEC-HEADER>\n"


COVER = _hdr_bytes(XLK_SID)          # a header that COVERS the fund under test -> the B1 guard proceeds
OTHER = _hdr_bytes("S000099999")     # a header for a DIFFERENT fund -> not_covered / prior-walk skip


def _cover_headers(url):
    """Answer a filing_header .txt Range GET for A/S/B with a COVERING header (the B1 guard proceeds), or
    None if `url` is not a header URL. Lets the existing mandate tests keep their bespoke body fetches."""
    if url in (_hdr_url(A), _hdr_url(S), _hdr_url(B)):
        return COVER
    return None


def _with_cover_headers(fetch):
    """Wrap a test's body fetch so a filing_header .txt URL it doesn't handle defaults to a COVERING header
    (the common case — the B1 guard proceeds, and the existing mandate tests need no change). A test that
    needs a non-covering / wrong-fund header answers that URL in its own fetch, which wins (no fallback)."""
    def wrapped(url, headers):
        try:
            return fetch(url, headers)
        except EdgarError:
            h = _cover_headers(url)
            if h is not None:
                return h
            raise
    return wrapped


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


def _subs_ASB():
    # newest-first: B (annual 2026), S (497 sticker), A (annual 2025). latest_prospectus -> B (newest of the
    # prospectus family); history -> [B, S, A]. The sticker sits BETWEEN the two annuals.
    return {"name": "Select Sector SPDR Trust", "filings": {"recent": {
        "form": ["485BPOS", "497", "485BPOS"], "accessionNumber": [B, S, A],
        "primaryDocument": [DOCB, "sticker.htm", "docA.htm"],
        "filingDate": ["2026-05-01", "2026-03-01", "2025-05-01"]}}}


def _subs_BWA():
    # newest-first: B (new annual), W (a WRONG-FUND filing over-attributed here by B1), A (the true prior
    # annual). latest_prospectus -> B; history -> [B, W, A]. W sits between the two annuals.
    return {"name": "Select Sector SPDR Trust", "filings": {"recent": {
        "form": ["485BPOS", "485BPOS", "485BPOS"], "accessionNumber": [B, W, A],
        "primaryDocument": [DOCB, "docW.htm", "docA.htm"],
        "filingDate": ["2026-05-01", "2026-04-01", "2025-05-01"]}}}


def _prefreeze(layout, accession, body):
    """Freeze a prospectus blob as a prior run's baseline would have (the §9c prior lives here)."""
    write_atomic(layout.prospectus_path(XLK_SID, accession, "index.html"), body)


def _deps(layout, registry, event_store, fetch):
    cfg, cfg_hash = load_config(CONFIG)
    clock = {"t": 0.0}
    edgar = EdgarClient("Test/1.0 (test@example.com)", fetch=_with_cover_headers(fetch),
                        clock=lambda: clock["t"],
                        sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                        persist=lambda name, body: write_atomic(layout.edgar_path(NOW[:10], name), body))
    return RunnerDeps(layout=layout, registry=registry, event_store=event_store, edgar_client=edgar,
                      price_ingest=PriceIngest(layout, fetch=lambda url, headers: b"",
                                               sleep=lambda _s: None),  # inert: _run_mandate never builds the panel
                      holdings_ingest=HoldingsIngest(layout, fetch=lambda u, h: b""),  # inert: dispersion never runs here
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


# === §9c prior reaches back ACROSS an intervening frozen sticker to the prior annual (item 3) =======

def test_mandate_prior_reaches_back_across_a_frozen_sticker_to_the_prior_annual(layout, registry):
    # A new annual (B) with an intervening 497 sticker (S) as the MOST-RECENT frozen filing. The §9c prior
    # must SKIP the sticker (not a full prospectus) and reach back to the prior ANNUAL (A), so the strategy
    # change between annuals is diffed — not baselined off the sticker (which would drop the change). Decision
    # docs/decisions/2026-07-18-mandate-supplement-not-a-prospectus.md. (Pre-item-3 the prior resolved to S,
    # scan baselined, and this emitted nothing — so this asserts the reach-back.)
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    funds.upsert(_entry(prospectus_accession=B))
    _prefreeze(layout, A, BASE)        # the prior annual (a full prospectus)
    _prefreeze(layout, S, STICKER)     # the intervening sticker — the newest frozen filing

    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs_ASB()).encode()
        if url == DOCB_URL:
            return SUBSTANTIVE
        raise EdgarError(f"no fixture for {url}", status=404)

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_mandate(deps, event_store, NOW, faults, runlog, funds)

    changed = event_store.read_system("mandate.changed")
    assert len(changed) == 1
    assert changed[0].payload["prior_accession"] == A     # reached ACROSS the sticker S to the prior annual
    assert changed[0].payload["current_accession"] == B
    assert changed[0].payload["summary"]
    assert faults == [] and runlog.sensors["mandate"] == "ran"


def test_mandate_with_only_a_frozen_sticker_prior_baselines_the_current_annual(layout, registry):
    # The only prior on file is a sticker (no prior FULL prospectus frozen) -> the §9c prior is None ->
    # mandate.scan baselines the current annual (freezes it), emits nothing. Not a fault, not a false diff.
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    funds.upsert(_entry(prospectus_accession=B))
    _prefreeze(layout, S, STICKER)     # only a sticker on file — no prior annual to diff against

    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs_ASB()).encode()
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


# === B1 over-attribution: the runner does not diff a filing that does not cover the series ===========

def test_mandate_over_attribution_current_filing_not_covering_the_series_emits_nothing(layout, registry):
    # latest_prospectus returns the trust's newest filing (B) for this series (B1 — the submissions doc has
    # no series dimension), but B's SGML header covers a DIFFERENT series. The runner must NOT freeze B under
    # XLK_SID and must NOT diff it -> nothing emitted, no fault (the expected B1 state, not an error).
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    funds.upsert(_entry(prospectus_accession=B))
    _prefreeze(layout, A, BASE)   # a covered prior exists; the CURRENT (B) simply isn't ours

    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs_AB()).encode()
        if url == _hdr_url(B):
            return OTHER          # B covers a DIFFERENT series -> not_covered (do not fetch/freeze DOCB)
        raise EdgarError(f"no fixture for {url}", status=404)   # DOCB_URL absent: any body fetch -> a fault

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_mandate(deps, event_store, NOW, faults, runlog, funds)

    assert event_store.read_system("mandate.changed") == []
    assert not ProspectusIngest(layout, deps.edgar_client).has_frozen(XLK_SID, B)  # never frozen under us
    assert faults == [] and runlog.sensors["mandate"] == "ran"  # not_covered is silent, and DOCB never fetched


def test_mandate_coverage_aware_prior_reaches_back_across_a_wrong_fund_frozen_filing(layout, registry):
    # The most-recent frozen prior (W) is a WRONG-FUND filing over-attributed here by B1; its SGML header
    # does not cover XLK_SID. The §9c prior walk must SKIP it (as it skips a supplement) and reach back to
    # the true covered prior annual (A), so the strategy change diffs A -> B, not against an unrelated fund.
    event_store = EventStore(layout, registry)
    funds = FundRegistry(layout, registry, event_store)
    funds.upsert(_entry(prospectus_accession=B))
    _prefreeze(layout, A, BASE)      # the true prior annual (covered)
    _prefreeze(layout, W, BASE)      # a wrong-fund filing frozen under this series (B1 pollution), newer than A

    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs_BWA()).encode()
        if url == DOCB_URL:
            return SUBSTANTIVE
        if url == _hdr_url(W):
            return OTHER             # W covers a DIFFERENT fund -> skipped by the coverage-aware prior walk
        raise EdgarError(f"no fixture for {url}", status=404)   # A/B headers default to COVER (the wrapper)

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_mandate(deps, event_store, NOW, faults, runlog, funds)

    changed = event_store.read_system("mandate.changed")
    assert len(changed) == 1
    assert changed[0].payload["prior_accession"] == A       # reached ACROSS the wrong-fund W to the true prior
    assert changed[0].payload["current_accession"] == B
    assert faults == [] and runlog.sensors["mandate"] == "ran"
