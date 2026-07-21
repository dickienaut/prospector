"""Mandate-diff sensor (spec §4d, milestone 4).

A new prospectus filing on a watched fund → extract its principal-investment-strategy section →
diff vs the prior filing → `mandate.changed` (a SILENT corroboration routed onto live leads, else
`_system`) on a real change; a `fault` when extraction is unreliable (flag, never mis-diff); nothing
on a cosmetic re-file. The targeted section is diffed, NOT the whole filing (the diff-trap). bs4 owns
HTML structure; this code owns which section + whether the text moved; the human owns significance.
Offline throughout — a realistically messy 485BPOS fixture, controlled deltas."""

from pathlib import Path

from prospector.ingest.edgar import EdgarClient, latest_prospectus
from prospector.ingest.prospectus import (ProspectusIngest, _is_heading, diff_mandate, extract_mandate,
                                          html_to_text, is_prospectus_supplement, parse_series_classes)
from prospector.sensors import mandate
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

FIXTURES = Path(__file__).parent / "fixtures" / "prospectus"
BASE = (FIXTURES / "485bpos_base.html").read_bytes()
STICKER = (FIXTURES / "497_supplement_sticker.html").read_bytes()  # a real 497 "Supplement dated…" sticker
SAI = (FIXTURES / "497_sai.html").read_bytes()                     # a real Statement of Additional Information
JPM_QA = (FIXTURES / "jpm_qa_prose_objective_synthetic.html").read_bytes()  # synthetic: a prose "Investment
#   objectives…" line + an unmatched Q&A strategy heading (the Case D false-extraction reproduction)
SPLIT_HEADING = (FIXTURES / "497_split_heading_tema.html").read_bytes()   # real: heading hard-wrapped
#   mid-phrase inside one text node ("Principal\nInvestment Strategies of the Fund")
TOC_SHADOW = (FIXTURES / "497_toc_shadows_section_vpff.html").read_bytes()  # real: a table-of-contents
#   entry precedes the real section, so the FIRST heading match bounded only a page number
LONG_STICKER = (FIXTURES / "497_supplement_long_declaration_pictet.html").read_bytes()  # real: a sticker
#   whose self-declaration names both funds it amends and so runs to 98 chars
HDR_JPM = (FIXTURES / "header_jpm_305575.txt").read_bytes()      # real SGML header: covers ONLY S000108870
#   (the B1 over-attribution proof — this 497 is frozen under three UNRELATED series in the live registry)
HDR_GS = (FIXTURES / "header_goldman_300911.txt").read_bytes()  # real SGML header: covers S000106340 (GCPB)
#   AND S000106341 (GINC) — a genuinely multi-fund filing, each series with its own fund name + ticker
GS_BODY = (FIXTURES / "goldman_multifund_body_300911.html").read_bytes()  # real rendered text of that
#   filing's two fund-summary blocks (re-wrapped one line per <p> for size — see the provenance sidecar)
GS_NAMES = ["Goldman Sachs Core Plus Bond ETF", "Goldman Sachs Income ETF"]  # its two covered fund names

UA = "Prospector-tests/1.0 (lyle.e.dickie@gmail.com)"
NOW = "2026-07-03T22:30:00Z"

CFG = {"mandate": None,
       "strategy_headings": ["principal investment strateg",
                             "what are the fund's main investment strateg",  # J.P. Morgan Q&A form (PR3)
                             "investment objective"],
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


# --- Case D: a prose line that merely OPENS with a strategy phrase is NOT the heading -------------
# docs/bugs/INDEX.md MANDATE-PROSE-HEADING. Bare `startswith` accepted a body line as the strategy heading
# and returned a RELIABLE extraction on garbage -> a spurious `mandate.changed` risk on a live lead. Strict
# heading matching (the phrase IS the heading, bar a bounded connective qualifier tail) closes it; a real
# full prospectus we cannot parse still FAULTS (the safe path), never a false change.

def test_is_heading_strict_rejects_prose_but_keeps_real_heading_variants():
    strat = ["principal investment strateg"]          # the mid-word stem (matches strategy / strategies)
    obj = ["investment objective"]
    # PROSE opening with the phrase -> NOT a heading (the Case D false match, both observed shapes)
    assert _is_heading("Investment objectives may change without shareholder approval.", obj, strict=True) is False
    assert _is_heading("Investment objective information for each Fund appears below", obj, strict=True) is False
    # REAL headings still match: exact, plural, connective qualifier tail, "and"-combined, stem singular
    assert _is_heading("Investment Objective", obj, strict=True) is True
    assert _is_heading("Investment Objectives", obj, strict=True) is True
    assert _is_heading("Investment Objective and Principal Investment Strategies", obj, strict=True) is True
    assert _is_heading("Principal Investment Strategies", strat, strict=True) is True
    assert _is_heading("Principal Investment Strategy", strat, strict=True) is True
    assert _is_heading("Principal Investment Strategies of the Fund", strat, strict=True) is True
    # a STOP heading with a long qualifier tail is still a heading (extract_mandate scans stops the same way)
    assert _is_heading("Principal Risks of Investing in the Fund", ["principal risk"], strict=True) is True


def test_is_heading_matches_a_qa_question_and_normalizes_smart_apostrophes():
    # A Q&A-format summary heading is a QUESTION ("…strategies?") rendered with a smart apostrophe (’ from
    # &rsquo;). The matcher treats the trailing "?" as terminal heading punctuation and normalizes ’->' so a
    # plain-apostrophe config pattern matches — while a question that runs on into a content word is still
    # rejected as prose (the guard holds). (PR3, docs/bugs/INDEX.md MANDATE-QA-QUESTION-HEADING.)
    pat = ["what are the fund's main investment strateg"]                      # config pattern: plain apostrophe
    assert _is_heading("What are the Fund’s main investment strategies?", pat, strict=True) is True   # curly ’ + ?
    assert _is_heading("What are the Fund's main investment strategies?", pat, strict=True) is True   # straight ' + ?
    assert _is_heading("What are the Fund’s main investment strategies", pat, strict=True) is True    # no "?"
    # a question that continues into a content word is NOT a heading (strict tail-check still bites)
    assert _is_heading("What are the fund's main investment strategies designed to do?", pat, strict=True) is False


def test_extract_recovers_the_jpm_qa_strategy_and_ignores_the_prose_objective_line():
    # The strategy sits under a Q&A heading ("What are the Fund's main investment strategies?"); the fund's
    # "investment objective" text is a body SENTENCE. With the Q&A heading recognized (PR3), extraction now
    # recovers the REAL strategy — and the prose objective line is still NOT mistaken for it (the Q&A heading
    # is the higher-priority target, and strict matching rejects the prose line anyway): recall + the guard.
    m = extract_mandate(JPM_QA, CFG)
    assert m["reliable"] is True
    assert m["heading"] == "What are the Fund’s main investment strategies?"   # the Q&A heading, not the prose
    assert "80% of its assets" in m["section"]                                  # the real strategy text...
    assert "may change without shareholder approval" not in m["section"]        # ...not the prose objective


def test_jpm_qa_cosmetic_refile_is_not_a_change():
    # A cosmetic re-file (new date only) leaves the Q&A strategy section byte-identical -> no change, no
    # spurious mandate.changed. (Pre-PR3 both sides faulted "heading not found"; now both extract cleanly.)
    refiled = JPM_QA.replace(b"January&nbsp;1,&nbsp;2026", b"January&nbsp;1,&nbsp;2027")
    d = diff_mandate(JPM_QA, refiled, CFG)
    assert d["reliable"] is True and d["changed"] is False


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


def _hdr(*series_ids, complete=True):
    """A DECLARED-SYNTHETIC SGML submission header covering the given series (used for the edge cases;
    the real filing shapes come from HDR_JPM / HDR_GS). `complete=False` drops the </SEC-HEADER> sentinel
    to model a truncated header (coverage unverifiable)."""
    body = "<SEC-HEADER>\n<SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    for sid in series_ids:
        body += f"<SERIES>\n<SERIES-ID>{sid}\n<SERIES-NAME>Fund {sid}\n"
    body += "</SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    if complete:
        body += "</SEC-HEADER>\n"
    return body.encode()


def _hdr_named(*pairs, complete=True):
    """A DECLARED-SYNTHETIC SGML header with explicit (series_id, fund_name) pairs — for multi-fund
    isolation tests where the SERIES-NAME must match a real body's fund-summary heading."""
    body = "<SEC-HEADER>\n<SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    for sid, name in pairs:
        body += f"<SERIES>\n<SERIES-ID>{sid}\n<SERIES-NAME>{name}\n"
    body += "</SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    if complete:
        body += "</SEC-HEADER>\n"
    return body.encode()


class FakeEdgar:
    """A stand-in EdgarClient whose filing_text serves fixture bytes per accession, recording calls
    (so a test can assert no fetch happened). filing_header serves the SGML SERIES/CLASS header the B1
    over-attribution guard consults (recorded separately, so body-fetch assertions are unaffected)."""

    def __init__(self, by_accession, headers_by_accession=None):
        self.by_accession = by_accession
        self.headers_by_accession = headers_by_accession or {}
        self.calls = []
        self.header_calls = []

    def filing_text(self, cik, accession, primary_doc):
        self.calls.append((cik, accession, primary_doc))
        return self.by_accession[accession]

    def filing_header(self, cik, accession):
        self.header_calls.append((cik, accession))
        return self.headers_by_accession[accession]


def _run(layout, by_accession, current, prior, active_lead_ids, *, prefreeze=None,
         headers=None, series_id=XLK):
    # Default: every accession's SGML header COVERS the scanned series, so the B1 over-attribution guard
    # PROCEEDS (the common single-fund case). A guard test overrides `headers` to model a filing that does
    # not cover this series (not_covered), a truncated header (review), or a multi-fund filing.
    hdrs = {acc: _hdr(series_id) for acc in by_accession}
    if headers:
        hdrs.update(headers)
    edgar = FakeEdgar(by_accession, hdrs)
    prospectus = ProspectusIngest(layout, edgar)
    if prefreeze:  # seed the prior filing's blob (as a prior run's baseline would have)
        prospectus.pull(series_id, CIK, prefreeze, "prior.htm")
        edgar.calls.clear()
    events = []

    def report_advisory(subsystem, message, series_id, extra=None):
        # Mirror the runner's §10 fault-reporter: a review-advisory fault into the same event stream, so
        # these unit tests read it exactly where the old raw `emit` fault landed (proving scan routes the
        # extraction-unreliable punt through report_advisory, never a raw fault write).
        events.append({"ts": NOW, "lead": SYSTEM_LEAD, "type": "fault",
                       "payload": {"subsystem": subsystem, "message": message, "series_id": series_id,
                                   "category": "review-advisory", **(extra or {})}})

    result = mandate.scan(series_id, "XLK", CIK, current, "cur.htm", prior, UNIVERSE, active_lead_ids,
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


# --- 497 supplement / SAI are not full prospectuses (the upstream noise-cut) -----------------------

def test_is_prospectus_supplement_classifies_sticker_sai_and_full():
    assert is_prospectus_supplement(STICKER) is True   # a 497 "Supplement dated…" sticker
    assert is_prospectus_supplement(SAI) is True        # a Statement of Additional Information
    assert is_prospectus_supplement(BASE) is False      # a full prospectus -> diffed normally


def test_scan_supplement_current_is_skipped_not_faulted(layout):
    # A new 497 sticker is not a full prospectus -> SKIP (the standing prospectus stays the mandate),
    # never a review-advisory "extraction unreliable" fault (the noise this cut removes).
    result, events, _ = _run(layout, {A: BASE, B: STICKER}, current=B, prior=A,
                             active_lead_ids={xcorr_lead_id([XLK, XLU])}, prefreeze=A)
    assert result["action"] == "supplement" and events == []


def test_scan_sai_current_is_skipped_not_faulted(layout):
    result, events, _ = _run(layout, {A: BASE, B: SAI}, current=B, prior=A,
                             active_lead_ids=set(), prefreeze=A)
    assert result["action"] == "supplement" and events == []


def test_scan_supplement_prior_is_baselined_not_contaminated(layout):
    # The prior on file is a sticker (a supplement frozen last cycle). Diffing a real full prospectus
    # AGAINST it mislabels the real filing extraction-unreliable (prior-blob contamination) -> baseline
    # from the current full prospectus instead, no advisory.
    result, events, _ = _run(layout, {A: STICKER, B: BASE}, current=B, prior=A,
                             active_lead_ids={xcorr_lead_id([XLK, XLU])}, prefreeze=A)
    assert result["action"] == "baseline" and events == []
    assert result["reason"] == "prior on file is a supplement, not a full prospectus"


# --- the B1 over-attribution guard: the SGML SERIES/CLASS header says which series a filing covers ----
# docs/bugs/INDEX.md B1 + MANDATE-MULTIFUND-SECTION. A prospectus resolves at REGISTRANT (CIK) level, so
# latest_prospectus hands the trust's newest filing to EVERY series of the CIK — including filings that do
# not cover a given fund. The filing's SGML header is the primary-source answer to WHICH series it covers.

def test_parse_series_classes_real_headers_report_true_coverage():
    jpm = parse_series_classes(HDR_JPM)
    assert jpm["complete"] and jpm["has_series_block"]
    assert set(jpm["series"]) == {"S000108870"}            # ONLY the All Country ETF's own new series...
    for claimed in ("S000101505", "S000101506", "S000105027"):
        assert claimed not in jpm["series"]                # ...NOT the 3 series the live registry attaches it to (B1)
    gs = parse_series_classes(HDR_GS)
    assert set(gs["series"]) == {"S000106340", "S000106341"}   # a GENUINELY multi-fund filing (GCPB + GINC)
    assert gs["series"]["S000106340"]["tickers"] == ["GCPB"]
    assert gs["series"]["S000106341"]["name"] == "Goldman Sachs Income ETF"


def test_parse_series_classes_three_distinct_signals_never_collapsed():
    # 1) TRUNCATED (the </SEC-HEADER> sentinel never arrives) -> complete False (coverage UNKNOWN -> fault)
    t = parse_series_classes(HDR_GS[: HDR_GS.find(b"</SEC-HEADER>")])
    assert t["complete"] is False
    # 2) complete but NO series block (older / non-fund form) -> benign "no series data", not "not covered"
    n = parse_series_classes(b"<SEC-HEADER>\n<ACCESSION-NUMBER>x\n</SEC-HEADER>\n")
    assert n["complete"] is True and n["has_series_block"] is False and n["series"] == {}
    # 3) malformed junk never crashes -> a dict with the three keys
    assert set(parse_series_classes(b"\x00 not sgml \xff")) == {"series", "complete", "has_series_block"}


def test_scan_over_attribution_filing_not_covering_this_series_is_skipped_no_freeze(layout):
    # THE B1 FIX: latest_prospectus handed us B (the trust's newest), but B's real SGML header covers a
    # DIFFERENT series (the J.P. Morgan 497 covers only S000108870). Scanning for XLK -> not_covered: do
    # not freeze B under XLK (no new pollution), do not diff, no fault (the expected B1 state, not an error).
    result, events, edgar = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                                 active_lead_ids={xcorr_lead_id([XLK, XLU])}, prefreeze=A,
                                 headers={B: HDR_JPM})
    assert result["action"] == "not_covered"
    assert events == []
    assert (CIK, B, "cur.htm") not in edgar.calls              # B was never fetched/frozen under XLK
    assert not ProspectusIngest(layout, edgar).has_frozen(XLK, B)


def test_scan_truncated_header_flags_for_review_never_diffs(layout):
    # A header we cannot verify (truncated) -> coverage UNKNOWN -> review-advisory, never a diff (§4d:
    # a false mandate.changed is worse than a missed one).
    result, events, _ = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                             active_lead_ids=set(), prefreeze=A, headers={B: _hdr(XLK, complete=False)})
    assert result["action"] == "flagged_unreliable"
    (ev,) = events
    assert ev["type"] == "fault" and ev["payload"]["category"] == "review-advisory"
    assert "manual review" in ev["payload"]["message"]
    assert not any(e["type"] == "mandate.changed" for e in events)


def test_scan_multifund_header_without_a_matching_body_block_faults_safely(layout):
    # The header says the filing covers >1 fund, but the body has no fund-summary block matching our series
    # (a header/body mismatch, or a fund whose name we can't tie to a block — name drift). Block isolation
    # FAULTS -> review-advisory, never a wrong diff (§4d). The successful-isolation path is proven on the
    # REAL Goldman body in test_extract_isolates_* below.
    result, events, _ = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                             active_lead_ids={xcorr_lead_id([XLK, XLU])}, prefreeze=A,
                             headers={B: _hdr(XLK, "S000000099")})
    assert result["action"] == "flagged_unreliable"
    assert not any(e["type"] == "mandate.changed" for e in events)


def test_scan_no_series_header_lone_claimant_proceeds(layout):
    # An older / non-fund form with no series block, claimed by only this series -> proceed (today's
    # whole-doc behaviour). Absence of a series block is "no series data", never exclusion.
    result, events, _ = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                             active_lead_ids=set(), prefreeze=A, headers={B: _hdr()})
    assert result["action"] == "mandate_changed"


def test_scan_no_series_header_shared_by_multiple_series_is_flagged(layout):
    # No series block AND the accession is frozen under >1 series -> we cannot attribute it -> review
    # (the series_sharing tripwire is the safe floor when the header can't disambiguate).
    ProspectusIngest(layout, FakeEdgar({B: BASE})).pull(XLU, CIK, B, "x.htm")  # a 2nd claimant, first...
    ProspectusIngest(layout, FakeEdgar({B: BASE})).pull(XLK, CIK, B, "x.htm")  # ...and us -> sharing == 2
    result, events, _ = _run(layout, {A: BASE, B: BASE}, current=B, prior=A, active_lead_ids=set(),
                             prefreeze=A, headers={B: _hdr()})
    assert result["action"] == "flagged_unreliable"
    assert events and "cannot attribute" in events[0]["payload"]["message"]


# --- lines come from block STRUCTURE, never from source whitespace (workstream-2 parser gaps) -----
#
# Both fixtures are RECORDED-REAL trimmed excerpts of filings that faulted in production on
# 2026-07-19; each carries a provenance header and was verified to reproduce the pre-fix failure.
# See docs/decisions/2026-07-19-mandate-extraction-structural-lines.md.

def test_html_to_text_keeps_a_hard_wrapped_heading_on_one_line():
    # The filer wrapped the heading INSIDE one text node: `<b>Principal\nInvestment Strategies of
    # the Fund</b>`. A newline in HTML text is insignificant whitespace (it renders as a space), so
    # the heading must survive as ONE line — splitting it there is what hid the section entirely.
    lines = html_to_text(SPLIT_HEADING).split("\n")
    assert "Principal Investment Strategies of the Fund" in lines
    assert "Principal" not in lines  # the fragment the old splitter produced


def test_html_to_text_still_breaks_lines_on_block_tags():
    # The other half of the contract: block structure MUST still break, or every heading would be
    # swallowed into the surrounding paragraph and nothing would be findable.
    out = html_to_text(b"<p>Principal Investment Strategies</p><p>The Fund invests.</p>"
                       b"<div>A<br>B</div><table><tr><td>C</td><td>D</td></tr></table>")
    assert out.split("\n") == ["Principal Investment Strategies", "The Fund invests.", "A", "B", "C", "D"]


def test_html_to_text_joins_inline_tags_with_a_space_not_a_break():
    # Inline tags must neither break the line nor run the words together.
    assert html_to_text(b"<p><b>Principal</b> <b>Investment Strategies</b> <i>of the Fund</i></p>") \
        == "Principal Investment Strategies of the Fund"


def test_extract_recovers_the_section_from_a_hard_wrapped_heading():
    r = extract_mandate(SPLIT_HEADING, CFG)
    assert r["reliable"] is True
    assert r["heading"] == "Principal Investment Strategies of the Fund"
    assert "actively managed exchange-traded fund" in r["section"]


def test_extract_scans_past_a_table_of_contents_entry_to_the_real_section():
    # The TOC lists "PRINCIPAL INVESTMENT STRATEGY", then the page number, then the next TOC entry
    # (a stop heading) — a perfectly heading-shaped line bounding a one-character "section". Taking
    # the FIRST match and failing on it reported the whole filing unreliable while the real section
    # sat further down. A candidate is the heading only if it bounds a section-shaped extraction.
    r = extract_mandate(TOC_SHADOW, CFG)
    assert r["reliable"] is True
    assert r["heading"] == "PRINCIPAL INVESTMENT STRATEGY"
    assert "80% of its net assets" in r["section"]
    assert len(r["section"]) > 1000          # the real section, not the page number


def test_continue_scan_still_faults_when_no_candidate_bounds_a_section():
    # The continue-scan must not become a "keep looking until something sticks" loosening: a filing
    # whose only heading-shaped candidates bound nothing is STILL unreliable (flag, never mis-diff),
    # and the reason reported is the FIRST candidate's, not the last.
    toc_only = (b"<p>PRINCIPAL INVESTMENT STRATEGY</p><p>2</p><p>PRINCIPAL RISKS</p><p>3</p>"
                b"<p>PRINCIPAL INVESTMENT STRATEGY</p><p>7</p><p>PERFORMANCE</p><p>9</p>")
    r = extract_mandate(toc_only, CFG)
    assert r["reliable"] is False
    assert r["reason"] == "section too short to be the strategy"
    assert r["section"] is None


def test_reflowed_prose_cannot_pose_as_a_heading():
    # The dangerous half of the split-lines bug: source newlines chopped a RISK sentence into
    # heading-shaped fragments, and `principal investment strategy to do so` passed the strict guard
    # (its tail opens with the connective "to") — returning a RELIABLE extraction of risk prose as
    # the strategy, the spurious-`mandate.changed` MANDATE-PROSE-HEADING class. Reflowed onto one
    # line the sentence is far over the 80-char heading bar, so the guard sees prose as prose.
    prose = (b"<p>Cash Transactions Risk. The Fund may, under certain circumstances, effect a portion\n"
             b"of its creations and redemptions for cash rather than in kind\n, but it is not a\n"
             b"principal investment strategy to do so\n. Partial cash creations are not a principal\n"
             b"risk of the Fund.</p>")
    assert "principal investment strategy to do so" not in html_to_text(prose).split("\n")
    assert extract_mandate(prose, CFG)["reliable"] is False


def test_split_heading_filing_diffs_instead_of_faulting(layout):
    # End to end: the filing that produced a real 2026-07-19 review-advisory now extracts, so a
    # substantive rewrite of its strategy is a `mandate.changed` rather than a manual-review punt.
    rewritten = SPLIT_HEADING.replace(b"at least 80%", b"at least 55%")
    d = diff_mandate(SPLIT_HEADING, rewritten, CFG)
    assert d["reliable"] is True and d["changed"] is True
    assert "55%" in d["summary"]


def test_a_sticker_declaring_itself_over_the_heading_bar_is_still_a_supplement():
    # NEAR-REGRESSION PIN. A heading is short (<=80 chars), but a sticker's self-declaration is one
    # LONG line — this real filing's is 98 ("Supplement dated July 15, 2026 to the Pictet AI &
    # Automation ETF's and Pictet Cleaner Planet ETF's currently effective Prospectus…"). The old
    # splitter only kept it under the bar by chopping it mid-phrase; once html_to_text reflows it,
    # holding declarations to the heading bar reclassified 11 real stickers as full prospectuses —
    # re-creating exactly the advisory noise the 2026-07-18 supplement cut removed.
    (decl,) = [ln for ln in html_to_text(LONG_STICKER).split("\n")
               if ln.lower().startswith("supplement dated")][:1]
    assert len(decl) > 80                                  # the bar the heading mode would apply
    assert is_prospectus_supplement(LONG_STICKER) is True


def test_the_looser_declaration_bar_does_not_admit_prose_mentioning_a_supplement():
    # The looser bar is safe only because declaration mode is ANCHORED at the start of the line: a
    # full prospectus that merely mentions a supplement mid-sentence must NOT be reclassified.
    prose = (b"<p>Principal Investment Strategies</p><p>The Fund invests in equity securities of "
             b"issuers in the information technology sector, as described more fully in any "
             b"supplement to this Prospectus that the Trust may file from time to time.</p>"
             b"<p>Principal Risks</p><p>You may lose money.</p>")
    assert is_prospectus_supplement(prose) is False
    assert extract_mandate(prose, CFG)["reliable"] is True  # still diffed normally


# --- multi-fund block isolation (Shape B) — the target fund's OWN block, not the first (2026-07-21) ---
# MANDATE-MULTIFUND-SECTION: a combined prospectus carries one strategy section PER FUND; the extractor took
# the FIRST, so every covered series diffed the first fund's strategy (2026-07-19: two Goldman series emitted
# BYTE-IDENTICAL mandate.changed). Isolation ties each series to ITS block by the SGML SERIES-NAME, then runs
# the ordinary strategy finder inside. Proven on the REAL Goldman body (GS_BODY) below.

OTHER = "S000000002"   # a second series holding the SAME filing in the store — the B1 shape
GS_A, GS_B = "S000106340", "S000106341"                        # the two covered Goldman series
GS_HDR = _hdr_named((GS_A, GS_NAMES[0]), (GS_B, GS_NAMES[1]))  # a header covering both, with real names
GS_CP75 = GS_BODY.replace(b"at least 80% of its net assets",   # move Core Plus's threshold ONLY (first hit)
                          b"at least 75% of its net assets", 1)


def test_series_sharing_still_lists_every_series_holding_an_accession(layout):
    # series_sharing survives as the no-series-header fallback tripwire in the guard. The structural tell:
    # the same accession frozen under >1 series. Read from the BLOB STORE, never the registry field (§9c).
    ingest = ProspectusIngest(layout, FakeEdgar({A: BASE}))
    ingest.pull(XLK, CIK, A, "d.htm")
    ingest.pull(OTHER, CIK, A, "d.htm")
    assert ingest.series_sharing(A) == sorted([XLK, OTHER])
    assert ingest.series_sharing("0000000000-00-000000") == []   # nothing frozen -> empty, never an error


def test_extract_isolates_each_funds_own_block_on_the_real_goldman_body():
    cp = extract_mandate(GS_BODY, CFG, fund_anchor=GS_NAMES[0], fund_names=GS_NAMES)
    inc = extract_mandate(GS_BODY, CFG, fund_anchor=GS_NAMES[1], fund_names=GS_NAMES)
    assert cp["reliable"] and inc["reliable"]
    assert cp["section"] != inc["section"]                       # each fund gets ITS OWN section...
    whole = extract_mandate(GS_BODY, CFG)                         # ...where the whole-doc extractor returns
    assert whole["reliable"] and whole["section"] == cp["section"]  # the FIRST fund (Core Plus) for BOTH


def test_extract_single_fund_or_no_anchor_is_whole_doc_unchanged():
    # Regression gate: a single covered name, or no anchor, is byte-identical to the pre-isolation path.
    base = extract_mandate(BASE, CFG)
    assert extract_mandate(BASE, CFG, fund_anchor="Tech Select", fund_names=["Tech Select"]) == base
    assert extract_mandate(BASE, CFG, fund_anchor=None, fund_names=GS_NAMES) == base


def test_extract_faults_when_the_anchor_matches_no_block():
    r = extract_mandate(GS_BODY, CFG, fund_anchor="Vanguard Nonexistent ETF",
                        fund_names=GS_NAMES + ["Vanguard Nonexistent ETF"])
    assert r["reliable"] is False and "not found for anchor" in r["reason"]


def test_extract_faults_when_the_anchor_is_a_substring_of_another_covered_name():
    # A name that is a PREFIX of another covered name — "Goldman Sachs Income ETF" ⊂ "Goldman Sachs Income
    # ETF Institutional Shares" — is a real substring, so the tie is unresolvable -> fault (the SOI
    # anti-ambiguity rule), never a guess by document order.
    names = GS_NAMES + ["Goldman Sachs Income ETF Institutional Shares"]
    r = extract_mandate(GS_BODY, CFG, fund_anchor="Goldman Sachs Income ETF", fund_names=names)
    assert r["reliable"] is False and "ambiguous" in r["reason"]


def test_diff_isolates_per_side_no_byte_identical_cross_fund_fire():
    # The 2026-07-19 failure, fixed. GS_CP75 (Core Plus at 75%) vs GS_BODY (Core Plus at 80%): isolated to
    # Core Plus -> a real change; isolated to Income (identical both sides) -> NO change (no cross-fund bleed).
    d_cp = diff_mandate(GS_CP75, GS_BODY, CFG, prior_anchor=GS_NAMES[0], prior_names=GS_NAMES,
                        current_anchor=GS_NAMES[0], current_names=GS_NAMES)
    d_inc = diff_mandate(GS_CP75, GS_BODY, CFG, prior_anchor=GS_NAMES[1], prior_names=GS_NAMES,
                         current_anchor=GS_NAMES[1], current_names=GS_NAMES)
    assert d_cp["reliable"] and d_cp["changed"] is True          # Core Plus moved...
    assert d_inc["reliable"] and d_inc["changed"] is False       # ...Income did not


def _run_gs(layout, series_id, prior_body, current_body):
    return _run(layout, {A: prior_body, B: current_body}, current=B, prior=A, active_lead_ids=set(),
                prefreeze=A, headers={A: GS_HDR, B: GS_HDR}, series_id=series_id)


def test_scan_multifund_isolates_the_target_block_and_stamps_covered_series(layout):
    # Scanning Core Plus (GS_A): its OWN section moved (75%->80%) -> mandate.changed, and the payload carries
    # neutral header-derived covered_series (NOT #122's shared_accession/sharing_series hedge, now removed).
    result, events, _ = _run_gs(layout, GS_A, prior_body=GS_CP75, current_body=GS_BODY)
    assert result["action"] == "mandate_changed"
    (ev,) = [e for e in events if e["type"] == "mandate.changed"]
    assert ev["payload"]["covered_series"] == sorted([GS_A, GS_B])
    assert "shared_accession" not in ev["payload"] and "sharing_series" not in ev["payload"]
    assert ev["payload"]["summary"]


def test_scan_multifund_the_other_fund_is_unchanged_no_cross_fire(layout):
    # Scanning Income (GS_B) on the SAME pair: Income's section is identical both sides -> unchanged, no
    # event. Pre-isolation both series diffed Core Plus and fired byte-identical events.
    result, events, _ = _run_gs(layout, GS_B, prior_body=GS_CP75, current_body=GS_BODY)
    assert result["action"] == "unchanged"
    assert not any(e["type"] == "mandate.changed" for e in events)


def test_scan_single_fund_filing_carries_no_provenance_marking(layout):
    # The normal single-fund case stays byte-clean — no covered_series (and never the old shared keys).
    _, events, _ = _run(layout, {A: BASE, B: SUBSTANTIVE}, current=B, prior=A,
                        active_lead_ids=set(), prefreeze=A)
    (ev,) = [e for e in events if e["type"] == "mandate.changed"]
    assert "covered_series" not in ev["payload"]
    assert "shared_accession" not in ev["payload"] and "sharing_series" not in ev["payload"]
