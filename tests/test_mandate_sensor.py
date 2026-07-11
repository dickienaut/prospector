"""Mandate-diff sensor (spec §4d, milestone 4).

A new prospectus filing on a watched fund → extract its principal-investment-strategy section →
diff vs the prior filing → `mandate.changed` (a SILENT corroboration routed onto live leads, else
`_system`) on a real change; a `fault` when extraction is unreliable (flag, never mis-diff); nothing
on a cosmetic re-file. The targeted section is diffed, NOT the whole filing (the diff-trap). bs4 owns
HTML structure; this code owns which section + whether the text moved; the human owns significance.
Offline throughout — a realistically messy 485BPOS fixture, controlled deltas."""

from pathlib import Path

from prospector.ingest.edgar import EdgarClient, latest_prospectus
from prospector.ingest.prospectus import ProspectusIngest, diff_mandate, extract_mandate
from prospector.sensors import mandate
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

FIXTURES = Path(__file__).parent / "fixtures" / "prospectus"
BASE = (FIXTURES / "485bpos_base.html").read_bytes()

UA = "Prospector-tests/1.0 (lyle.e.dickie@gmail.com)"
NOW = "2026-07-03T22:30:00Z"

CFG = {"mandate": None, "strategy_headings": ["principal investment strateg", "investment objective"],
       "stop_headings": ["principal risk", "principal investment risk", "performance",
                         "fees and expenses", "portfolio management", "purchase and sale",
                         "tax information"],
       "min_section_chars": 80, "max_section_lines": 400}

# --- controlled deltas off the messy base fixture (the strategy WORDS are what matters) -----------

# Cosmetic: a new prospectus date, a lower fee, and reflowed whitespace inside the strategy — the
# strategy WORDS are byte-identical after normalization.
COSMETIC = (BASE.replace(b"July&nbsp;1,&nbsp;2025", b"July&nbsp;1,&nbsp;2026")
                .replace(b"0.09%", b"0.08%")
                .replace(b"invest at least 95% of its total\nassets",
                         b"invest at least 95%&nbsp; of its  total assets"))
# Substantive: the strategy itself is rewritten (method, threshold, and sector concentration).
SUBSTANTIVE = (BASE.replace(b"employs a replication strategy",
                            b"employs a representative sampling strategy")
                   .replace(b"at least 95% of its total", b"at least 80% of its total")
                   .replace(b"information technology sector", b"health care sector"))
# Unreliable: the strategy/objective headings are renamed to nonstandard wording -> heading not found.
UNRELIABLE = (BASE.replace(b"Principal&nbsp;Investment&nbsp;Strategies", b"Summary of How the Fund Invests")
                  .replace(b"Investment Objective", b"Goal of the Fund"))


# --- extraction + diff (the spine) ---------------------------------------------------------------

def test_extract_prefers_the_strategies_section_over_the_objective():
    m = extract_mandate(BASE, CFG)
    assert m["reliable"] and m["heading"] == "Principal Investment Strategies"  # not "Investment Objective"
    assert "replication strategy" in m["section"]
    assert "information technology sector" in m["section"]
    assert "bar chart" not in m["section"]           # bounded — stops at Principal Risks / Performance


def test_cosmetic_refile_is_not_a_change():
    d = diff_mandate(BASE, COSMETIC, CFG)
    assert d["reliable"] and d["changed"] is False   # fee/date/whitespace churn is not a mandate change
    assert d["summary"] is None


def test_substantive_rewrite_is_a_change_with_a_summary():
    d = diff_mandate(BASE, SUBSTANTIVE, CFG)
    assert d["reliable"] and d["changed"] is True
    assert d["summary"] and ("representative sampling" in d["summary"] or "health care" in d["summary"])


def test_unreliable_extraction_is_flagged_not_diffed():
    d = diff_mandate(BASE, UNRELIABLE, CFG)
    assert d["reliable"] is False and d["changed"] is False
    assert d["reason"] == "strategy heading not found"


def test_diff_mandate_never_judges_significance():
    # The structure/meaning/significance boundary: diff_mandate reports whether the text moved,
    # NEVER whether the move is meaningful — no significance/verdict field leaks out.
    assert set(diff_mandate(BASE, SUBSTANTIVE, CFG)) == {"changed", "reliable", "summary", "reason"}


# --- EDGAR surface: latest_prospectus + the Archives fetch URL ------------------------------------

def test_latest_prospectus_picks_most_recent_prospectus_form_with_primary_doc():
    subs = {"filings": {"recent": {
        "form": ["NPORT-P", "485BPOS", "497", "8-K"],
        "accessionNumber": ["a0", "a1", "a2", "a3"],
        "primaryDocument": ["d0.htm", "d1.htm", "d2.htm", "d3.htm"],
        "filingDate": ["2026-06-01", "2026-05-01", "2026-07-01", "2026-07-15"]}}}
    assert latest_prospectus(subs) == {"accession": "a2", "primary_doc": "d2.htm",
                                       "form": "497", "filing_date": "2026-07-01"}
    # no prospectus-family filing -> None (8-K is not a prospectus)
    assert latest_prospectus({"filings": {"recent": {
        "form": ["8-K"], "accessionNumber": ["x"], "primaryDocument": ["d.htm"],
        "filingDate": ["2026-01-01"]}}}) is None


def test_filing_text_builds_the_archives_url_and_fetches():
    seen = {}

    def fetch(url, headers):
        seen["url"] = url
        return b"<html>ok</html>"

    client = EdgarClient(UA, fetch=fetch, clock=lambda: 0.0, sleep=lambda s: None)
    body = client.filing_text(1516212, "0001193125-26-291833", "d119140d485bpos.htm")
    assert body == b"<html>ok</html>"
    assert seen["url"] == ("https://www.sec.gov/Archives/edgar/data/1516212/"
                           "000119312526291833/d119140d485bpos.htm")  # dashes stripped from the accession


# --- the scan driver -----------------------------------------------------------------------------

CIK = 1516212
XLK, XLU = "S000006415", "S000006416"
UNIVERSE = [XLK, XLU]
A = "0001193125-25-280452"   # prior filing
B = "0001193125-26-291833"   # new filing


class FakeEdgar:
    """A stand-in EdgarClient whose filing_text serves fixture bytes per accession, recording calls
    (so a test can assert no fetch happened)."""

    def __init__(self, by_accession):
        self.by_accession = by_accession
        self.calls = []

    def filing_text(self, cik, accession, primary_doc):
        self.calls.append((cik, accession, primary_doc))
        return self.by_accession[accession]


def _run(layout, by_accession, current, prior, active_lead_ids, *, prefreeze=None):
    edgar = FakeEdgar(by_accession)
    prospectus = ProspectusIngest(layout, edgar)
    if prefreeze:  # seed the prior filing's blob (as a prior run's baseline would have)
        prospectus.pull(XLK, CIK, prefreeze, "prior.htm")
        edgar.calls.clear()
    events = []

    def report_advisory(subsystem, message, series_id, extra=None):
        # Mirror the runner's §10 fault-reporter: a review-advisory fault into the same event stream, so
        # these unit tests read it exactly where the old raw `emit` fault landed (proving scan routes the
        # extraction-unreliable punt through report_advisory, never a raw fault write).
        events.append({"ts": NOW, "lead": SYSTEM_LEAD, "type": "fault",
                       "payload": {"subsystem": subsystem, "message": message, "series_id": series_id,
                                   "category": "review-advisory", **(extra or {})}})

    result = mandate.scan(XLK, "XLK", CIK, current, "cur.htm", prior, UNIVERSE, active_lead_ids,
                          prospectus, CFG, NOW, events.append, report_advisory)
    return result, events, edgar


def test_scan_first_sight_freezes_a_baseline_no_event(layout):
    result, events, edgar = _run(layout, {A: BASE}, current=A, prior=None, active_lead_ids=set())
    assert result["action"] == "baseline" and events == []
    assert edgar.calls == [(CIK, A, "cur.htm")]                # fetched + froze the baseline once


def test_scan_no_new_filing_does_not_refetch_or_emit(layout):
    result, events, edgar = _run(layout, {A: BASE}, current=A, prior=A, active_lead_ids=set(),
                                 prefreeze=A)
    assert result["action"] == "none" and events == []
    assert edgar.calls == []                                   # already frozen -> no fetch


def test_scan_substantive_change_routes_mandate_changed_onto_live_leads(layout):
    pair = xcorr_lead_id([XLK, XLU])
    result, events, _ = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                             active_lead_ids={pair}, prefreeze=A)
    assert result["action"] == "mandate_changed" and result["emitted_to"] == [pair]
    (ev,) = events
    assert ev["lead"] == pair and ev["type"] == "mandate.changed"
    assert ev["payload"]["series_id"] == XLK
    assert ev["payload"]["prior_accession"] == A and ev["payload"]["current_accession"] == B
    assert ev["payload"]["summary"]


def test_scan_substantive_change_with_no_live_lead_records_on_system(layout):
    result, events, _ = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                             active_lead_ids=set(), prefreeze=A)
    assert result["emitted_to"] == [SYSTEM_LEAD]
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["type"] == "mandate.changed"


def test_scan_cosmetic_refile_emits_nothing(layout):
    result, events, _ = _run(layout, {A: BASE, B: COSMETIC}, current=B, prior=A,
                             active_lead_ids={xcorr_lead_id([XLK, XLU])}, prefreeze=A)
    assert result["action"] == "unchanged" and events == []


def test_scan_unreliable_extraction_faults_and_emits_no_mandate_changed(layout):
    result, events, _ = _run(layout, {A: BASE, B: UNRELIABLE}, current=B, prior=A,
                             active_lead_ids={xcorr_lead_id([XLK, XLU])}, prefreeze=A)
    assert result["action"] == "flagged_unreliable"
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["type"] == "fault"
    assert ev["payload"]["subsystem"] == "mandate" and "manual review" in ev["payload"]["message"]
    # §10: it is a REVIEW-ADVISORY routed through report_advisory (not an operational fault, not a raw emit).
    assert ev["payload"]["category"] == "review-advisory" and ev["payload"]["series_id"] == XLK
    assert not any(e["type"] == "mandate.changed" for e in events)
