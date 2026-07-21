"""EdgarClient + resolve_ticker: SEC fair-access discipline (declared UA, rate cap, backoff)
and the §2 resolution flow (CONTRACT — the HECO rule, failed-resolution path; §10 tests 1-2).
Offline: fake fetches close over the recorded fixtures in tests/fixtures/edgar/."""

import json
from pathlib import Path

import pytest

from prospector.ingest.edgar import (MF_TICKERS_URL, PROSPECTUS_FORMS, EdgarClient, EdgarError,
                                     Resolution, ResolutionFailure, SoiTarget, latest_soi,
                                     resolve_series, resolve_soi_document, resolve_soi_target,
                                     resolve_ticker)

FIXTURES = Path(__file__).parent / "fixtures"
EDGAR = FIXTURES / "edgar"

HECO_URL = "https://data.sec.gov/submissions/CIK0001516212.json"
SECTORS_URL = "https://data.sec.gov/submissions/CIK0001064641.json"

UA = "Prospector-tests/1.0 (lyle.e.dickie@gmail.com)"

_FIXTURE_BY_URL = {
    MF_TICKERS_URL: "company_tickers_mf.json",
    HECO_URL: "heco_submissions.json",
    SECTORS_URL: "sectors_submissions.json",
}


def fixture_fetch(url, headers):
    if url not in _FIXTURE_BY_URL:
        raise EdgarError(f"no fixture for {url}", status=404)
    return (EDGAR / _FIXTURE_BY_URL[url]).read_bytes()


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_client(fetch, **over):
    """Client with a fake clock whose injected sleep advances it — no real waiting."""
    clock = FakeClock()
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    kwargs = dict(fetch=fetch, clock=clock, sleep=sleep)
    kwargs.update(over)
    return EdgarClient(UA, **kwargs), clock, sleeps


# -- User-Agent on EVERY request (SEC 403s undeclared UAs) ----------------------

def test_user_agent_header_on_every_request():
    seen = []

    def recording(url, headers):
        seen.append((url, dict(headers)))
        return fixture_fetch(url, headers)

    client, _, _ = make_client(recording)
    client.mf_tickers()
    client.submissions(1516212)
    client.submissions(1064641)
    assert [url for url, _ in seen] == [MF_TICKERS_URL, HECO_URL, SECTORS_URL]
    assert all(headers["User-Agent"] == UA for _, headers in seen)


def test_undeclared_user_agent_rejected_at_construction():
    with pytest.raises(ValueError):
        EdgarClient("  ", fetch=fixture_fetch)


# -- rate limiter ----------------------------------------------------------------

def test_rate_limiter_never_exceeds_max_per_sec():
    clock = FakeClock()
    starts, sleeps = [], []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    def timed(url, headers):
        starts.append(clock())
        return fixture_fetch(url, headers)

    client = EdgarClient(UA, fetch=timed, max_per_sec=4.0, clock=clock, sleep=sleep)
    for _ in range(8):
        client.mf_tickers()
    # Request starts spaced >= 1/max_per_sec: never more than 4 requests in any second.
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(gap >= 0.25 - 1e-9 for gap in gaps)
    # First request goes straight through; the other 7 each waited out the interval.
    assert len(sleeps) == 7
    assert all(s == pytest.approx(0.25) for s in sleeps)


def test_rate_limiter_no_sleep_when_requests_already_spaced():
    client, clock, sleeps = make_client(fixture_fetch, max_per_sec=4.0)
    client.mf_tickers()
    clock.now += 1.0  # a slow caller outruns the limiter
    client.mf_tickers()
    assert sleeps == []


# -- backoff on 429/403 ------------------------------------------------------------

def test_backoff_retries_429_then_succeeds():
    attempts = []

    def flaky(url, headers):
        attempts.append(url)
        if len(attempts) <= 2:
            raise EdgarError("slow down", status=429)
        return fixture_fetch(url, headers)

    client, _, sleeps = make_client(flaky)
    parsed = client.mf_tickers()
    assert parsed["fields"] == ["cik", "seriesId", "classId", "symbol"]
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff between attempts


def test_backoff_permanent_403_raises_typed_error_after_capped_retries():
    attempts = []

    def denied(url, headers):
        attempts.append(url)
        raise EdgarError("denied", status=403)

    client, _, sleeps = make_client(denied)
    with pytest.raises(EdgarError) as exc_info:
        client.mf_tickers()
    assert exc_info.value.status == 403
    assert len(attempts) == 3  # capped, not infinite
    assert sleeps == [1.0, 2.0]


def test_backoff_retries_transient_5xx_then_succeeds():
    # N7 mirror: submissions/SOI are fetched every tick and had the identical gap — a transient 5xx must
    # be retried, not dropped on attempt 1. RED before the edgar mirror (503 not in the retry set).
    attempts = []

    def flaky(url, headers):
        attempts.append(url)
        if len(attempts) == 1:
            raise EdgarError("service unavailable", status=503)
        return fixture_fetch(url, headers)

    client, _, sleeps = make_client(flaky)
    parsed = client.mf_tickers()
    assert parsed["fields"] == ["cik", "seriesId", "classId", "symbol"]
    assert len(attempts) == 2 and sleeps == [1.0]


def test_backoff_retries_transport_error_status_none():
    # A transport/timeout error becomes an EdgarError with status None (the httpx.HTTPError catch) — the
    # retry loop must treat it as transient rather than let it escape mid-tick (N7 mirror).
    attempts = []

    def flaky(url, headers):
        attempts.append(url)
        if len(attempts) == 1:
            raise EdgarError(f"GET {url} failed: ReadTimeout")  # status defaults to None
        return fixture_fetch(url, headers)

    client, _, sleeps = make_client(flaky)
    client.mf_tickers()
    assert len(attempts) == 2 and sleeps == [1.0]


def test_non_retryable_status_raises_immediately():
    attempts = []

    def missing(url, headers):
        attempts.append(url)
        raise EdgarError("gone", status=404)

    client, _, sleeps = make_client(missing)
    with pytest.raises(EdgarError):
        client.submissions(999)
    assert len(attempts) == 1
    assert sleeps == []


# -- resolve_ticker: the HECO rule (spec §10 test 1) ---------------------------------

def _heco_expected():
    return json.loads((FIXTURES / "heco.json").read_text(encoding="utf-8"))["expected_entry"]


def test_resolve_heco_matches_expected_entry():
    expected = _heco_expected()
    client, _, _ = make_client(fixture_fetch)
    r = resolve_ticker("HECO", client)
    assert isinstance(r, Resolution)
    assert r.series_id == expected["series_id"] == "S000087750"
    assert r.class_ids == expected["class_ids"] == ["C000253658"]
    assert r.cik == expected["cik"] == 1516212
    assert r.name == expected["issuer"] == "SSGA Active Trust"  # trust name, not the fund's
    assert r.prospectus_accession == expected["prospectus_accession"]
    assert r.ticker == "HECO"
    # The accession really is a prospectus-family filing in the recorded submissions.
    subs = json.loads((EDGAR / "heco_submissions.json").read_text(encoding="utf-8"))
    recent = subs["filings"]["recent"]
    i = recent["accessionNumber"].index(r.prospectus_accession)
    assert recent["form"][i] in PROSPECTUS_FORMS


def test_resolve_heco_case_insensitive():
    client, _, _ = make_client(fixture_fetch)
    assert resolve_ticker("heco", client) == resolve_ticker("HECO", client)


def test_resolve_xlk_under_sector_trust():
    client, _, _ = make_client(fixture_fetch)
    r = resolve_ticker("XLK", client)
    assert isinstance(r, Resolution)
    assert r.series_id == "S000006415"
    assert r.cik == 1064641
    assert r.class_ids == ["C000017601"]
    assert r.name == "SELECT SECTOR SPDR TRUST"
    assert r.ticker == "XLK"
    # prospectus_accession is the MOST RECENT prospectus-family filing in the fixture.
    subs = json.loads((EDGAR / "sectors_submissions.json").read_text(encoding="utf-8"))
    recent = subs["filings"]["recent"]
    rows = [(d, a) for a, d, f in zip(recent["accessionNumber"], recent["filingDate"],
                                      recent["form"]) if f in PROSPECTUS_FORMS]
    assert r.prospectus_accession == max(rows)[1]


def test_resolve_aggregates_all_class_rows_for_the_series():
    # LACAX and ACRNX are two classes of the same (cik, series) in the mf map fixture.
    def fetch(url, headers):
        if url == "https://data.sec.gov/submissions/CIK0000002110.json":
            return json.dumps({
                "cik": "0000002110", "name": "COLUMBIA ACORN TRUST",
                "filings": {"recent": {"accessionNumber": ["0000002110-26-000001"],
                                       "filingDate": ["2026-01-15"], "form": ["485BPOS"],
                                       "primaryDocument": ["doc.htm"]}}}).encode("utf-8")
        return fixture_fetch(url, headers)

    client, _, _ = make_client(fetch)
    r = resolve_ticker("LACAX", client)
    assert isinstance(r, Resolution)
    assert r.series_id == "S000009184"
    assert r.class_ids == ["C000024954", "C000024957"]
    assert r.ticker == "LACAX"


# -- resolve_ticker: failure paths (spec §10 test 2 feeds on these) -------------------

def test_resolve_zzzq_not_in_mf_map():
    scenario = json.loads((FIXTURES / "resolution_failure.json").read_text(encoding="utf-8"))
    client, _, _ = make_client(fixture_fetch)
    r = resolve_ticker(scenario["ticker"], client)
    assert isinstance(r, ResolutionFailure)
    assert r.ticker == "ZZZQ"
    assert r.reason == "not_in_mf_map"
    assert r.detail  # countable AND explicable, never silent


def test_resolve_http_error_on_submissions():
    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return fixture_fetch(url, headers)
        raise EdgarError(f"GET {url} -> HTTP 500", status=500)

    client, _, _ = make_client(fetch)
    r = resolve_ticker("HECO", client)
    assert isinstance(r, ResolutionFailure)
    assert r.reason == "http_error"
    assert "CIK0001516212" in r.detail


def test_resolve_http_error_on_mf_map():
    def fetch(url, headers):
        raise EdgarError("denied", status=403)

    client, _, _ = make_client(fetch)
    r = resolve_ticker("HECO", client)
    assert isinstance(r, ResolutionFailure)
    assert r.reason == "http_error"


def test_resolve_no_prospectus():
    def fetch(url, headers):
        if url == HECO_URL:  # a registrant with filings, none prospectus-family
            return json.dumps({
                "cik": "0001516212", "name": "SSGA Active Trust",
                "filings": {"recent": {"accessionNumber": ["0001193125-26-000001"],
                                       "filingDate": ["2026-05-01"], "form": ["NPORT-P"],
                                       "primaryDocument": ["doc.xml"]}}}).encode("utf-8")
        return fixture_fetch(url, headers)

    client, _, _ = make_client(fetch)
    r = resolve_ticker("HECO", client)
    assert isinstance(r, ResolutionFailure)
    assert r.reason == "no_prospectus"


# -- raw persistence (freeze the substrate, §3) ----------------------------------------

def test_persist_receives_raw_bytes_for_each_successful_fetch():
    records = []
    client, _, _ = make_client(fixture_fetch, persist=lambda name, body: records.append((name, body)))
    client.mf_tickers()
    client.submissions(1516212)
    assert records == [
        ("company_tickers_mf.json", (EDGAR / "company_tickers_mf.json").read_bytes()),
        ("CIK0001516212.json", (EDGAR / "heco_submissions.json").read_bytes()),
    ]


def test_persist_not_called_on_failure():
    records = []

    def denied(url, headers):
        raise EdgarError("denied", status=403)

    client, _, _ = make_client(denied, persist=lambda name, body: records.append(name))
    with pytest.raises(EdgarError):
        client.mf_tickers()
    assert records == []


# -- I1: resolve on the DETECTED series, not the re-derived ticker (the HECO reused-ticker rule) -----

def _mf(rows):
    """A minimal MF ticker map: rows are [cik, seriesId, classId, symbol]."""
    return {"fields": ["cik", "seriesId", "classId", "symbol"], "data": rows}


def _prospectus_subs(name, accession, date="2026-06-01"):
    return {"name": name, "filings": {"recent": {
        "accessionNumber": [accession], "filingDate": [date], "form": ["485BPOS"],
        "primaryDocument": ["p.htm"]}}}


def _reuse_client():
    """A client whose MF map lists ticker REUSE under BOTH an old and a new (cik, series) — the
    ticker-reuse transition window (the HECO case), where matches[0] is a coin-flip."""
    mf = _mf([[111, "S000000111", "C000000111", "REUSE"],
              [222, "S000000222", "C000000222", "REUSE"]])

    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return json.dumps(mf).encode()
        if url == "https://data.sec.gov/submissions/CIK0000000222.json":
            return json.dumps(_prospectus_subs("New Trust", "0000000222-26-000001")).encode()
        if url == "https://data.sec.gov/submissions/CIK0000000111.json":
            return json.dumps(_prospectus_subs("Old Trust", "0000000111-20-000001",
                                               "2020-01-01")).encode()
        raise EdgarError(f"no fixture for {url}", status=404)

    client, _, _ = make_client(fetch)
    return client


def test_i1_reused_ticker_is_ambiguous_to_resolve_ticker():
    # On a reuse transition the ticker alone maps to two (cik, series): resolve_ticker must FAULT, never
    # silently pick matches[0] by document order (the trap I1 exists to defeat).
    r = resolve_ticker("REUSE", _reuse_client())
    assert isinstance(r, ResolutionFailure) and r.reason == "ambiguous_symbol"
    assert "S000000111" in r.detail and "S000000222" in r.detail


def test_i1_resolve_series_keys_on_the_detected_series():
    # Threaded the DETECTED series, resolution is unambiguous and correct — the series is the key, never
    # the ticker. The SAME ticker resolves to whichever series was detected.
    client = _reuse_client()
    new = resolve_series("S000000222", "REUSE", client)
    assert isinstance(new, Resolution)
    assert new.series_id == "S000000222" and new.cik == 222
    assert new.prospectus_accession == "0000000222-26-000001" and new.ticker == "REUSE"
    old = resolve_series("S000000111", "REUSE", client)
    assert isinstance(old, Resolution) and old.series_id == "S000000111" and old.cik == 111


def test_resolve_series_absent_series_is_not_in_mf_map():
    r = resolve_series("S000999999", "REUSE", _reuse_client())
    assert isinstance(r, ResolutionFailure) and r.reason == "not_in_mf_map"
    assert "S000999999" in r.detail


def test_resolve_series_aggregates_all_class_rows():
    # A multi-class series: resolve_series collects every class id for the (cik, series), like the
    # ticker path, but keyed on the detected series.
    mf = _mf([[300, "S000000300", "C000000301", "MCLS"],
              [300, "S000000300", "C000000302", "MCLS2"]])

    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return json.dumps(mf).encode()
        if url == "https://data.sec.gov/submissions/CIK0000000300.json":
            return json.dumps(_prospectus_subs("Multi Trust", "0000000300-26-000001")).encode()
        raise EdgarError("no fixture", status=404)

    client, _, _ = make_client(fetch)
    r = resolve_series("S000000300", "MCLS", client)
    assert isinstance(r, Resolution) and r.class_ids == ["C000000301", "C000000302"]


# -- B2: older filings under filings.files[] are flagged, never silently no_prospectus ---------------

def test_b2_older_filings_unread_is_flagged_not_silent_no_prospectus():
    # A long-lived registrant: no prospectus in filings.recent, but older pages exist in filings.files[].
    # 'no prospectus in recent' is INCONCLUSIVE — flag it (pagination deferred), never wrongly queue it.
    base_recent = {"accessionNumber": ["x-26-1"], "filingDate": ["2026-01-01"],
                   "form": ["NPORT-P"], "primaryDocument": ["d.xml"]}  # a filing, but not prospectus-family
    with_files = {"name": "Ancient Trust", "filings": {
        "recent": base_recent,
        "files": [{"name": "CIK0000000500-submissions-001.json", "filingCount": 1200,
                   "filingFrom": "1998-01-01", "filingTo": "2010-01-01"}]}}
    no_files = {"name": "Small Trust", "filings": {"recent": base_recent}}  # recent is complete

    def client_for(subs):
        def fetch(url, headers):
            if url == MF_TICKERS_URL:
                return json.dumps(_mf([[500, "S000000500", "C000000500", "OLD"]])).encode()
            if url == "https://data.sec.gov/submissions/CIK0000000500.json":
                return json.dumps(subs).encode()
            raise EdgarError("no fixture", status=404)
        c, _, _ = make_client(fetch)
        return c

    for resolver in (lambda c: resolve_ticker("OLD", c),
                     lambda c: resolve_series("S000000500", "OLD", c)):
        flagged = resolver(client_for(with_files))
        assert isinstance(flagged, ResolutionFailure) and flagged.reason == "older_filings_unread"
        assert "filings.files[]" in flagged.detail
        # Control: with no older pages, 'no prospectus in recent' IS conclusive.
        assert resolver(client_for(no_files)).reason == "no_prospectus"


# -- SOI-fetch (§9b): latest_soi form-priority selection --------------------------------
# Synthetic submissions dicts (obviously test-constructed, in-band) — the selection logic is a pure
# function of the columnar `filings.recent`, so no recorded fixture is needed here.

def _subs(rows):
    """rows: list of (form, filingDate, accessionNumber, primaryDocument) -> a submissions dict."""
    forms, dates, accs, docs = ([r[i] for r in rows] for i in range(4))
    return {"filings": {"recent": {"form": forms, "filingDate": dates,
                                   "accessionNumber": accs, "primaryDocument": docs}}}


def test_latest_soi_prefers_nport_ex_even_when_ncsr_is_newer():
    # Priority-tier, NOT newest-across-forms: the reader is verified only on NPORT-EX, so a newer N-CSR
    # must never win over an NPORT-EX. (NPORT-P is the non-EX N-PORT XML — no GICS — and is never picked.)
    subs = _subs([
        ("NPORT-EX", "2025-07-31", "0001410368-25-011151", "primary_doc.xml"),
        ("N-CSR",    "2025-12-01", "0000000000-25-000002", "ncsr.htm"),        # newer, lower tier
        ("NPORT-P",  "2025-08-15", "0000000000-25-000003", "primary_doc.xml"),  # never selected
    ])
    got = latest_soi(subs)
    assert got["form"] == "NPORT-EX"
    assert got["accession"] == "0001410368-25-011151"
    assert got["filing_date"] == "2025-07-31"


def test_latest_soi_ignores_nport_non_ex_and_unknown_forms():
    subs = _subs([
        ("NPORT-P", "2025-08-15", "acc1", "primary_doc.xml"),
        ("485BPOS", "2025-09-01", "acc2", "pros.htm"),
    ])
    assert latest_soi(subs) is None


def test_latest_soi_falls_back_through_the_tiers():
    # No NPORT-EX -> the next tier (N-CSR) wins over the lowest (N-CSRS), regardless of date.
    subs = _subs([
        ("N-CSRS", "2025-11-01", "acc-s", "ncsrs.htm"),   # newer, but lowest tier
        ("N-CSR",  "2025-09-01", "acc-r", "ncsr.htm"),
    ])
    got = latest_soi(subs)
    assert got["form"] == "N-CSR" and got["accession"] == "acc-r"


def test_latest_soi_same_day_tie_keeps_the_later_filing():
    # `recent` is newest-first, so strict > keeps the earlier index (the later filing) on a same-day tie.
    subs = _subs([
        ("NPORT-EX", "2025-07-31", "acc-later", "primary_doc.xml"),   # listed first == later filing
        ("NPORT-EX", "2025-07-31", "acc-earlier", "primary_doc.xml"),
    ])
    assert latest_soi(subs)["accession"] == "acc-later"


def test_latest_soi_missing_columns_returns_none():
    assert latest_soi({}) is None
    assert latest_soi({"filings": {"recent": {}}}) is None


# -- SOI-fetch (§9b): filing_index + resolve_soi_document -------------------------------

def _index(names):
    return {"directory": {"item": [{"name": n} for n in names]}}


def test_filing_index_url_shape_and_persist_name():
    seen = {}

    def fetch(url, headers):
        seen["url"] = url
        return json.dumps(_index(["x.htm"])).encode()

    records = []
    client, _, _ = make_client(fetch, persist=lambda name, body: records.append(name))
    idx = client.filing_index(1516212, "0001410368-25-011151")
    assert seen["url"] == ("https://www.sec.gov/Archives/edgar/data/1516212/"
                           "000141036825011151/index.json")
    assert idx["directory"]["item"][0]["name"] == "x.htm"
    assert records == ["000141036825011151_index.json"]  # frozen via persist (§3), like every pull


def test_filing_index_retries_429_via_get():
    # index.json fetch inherits the throttle + backoff of _get, same as mf_tickers/submissions.
    attempts = []

    def flaky(url, headers):
        attempts.append(url)
        if len(attempts) <= 1:
            raise EdgarError("slow down", status=429)
        return json.dumps(_index([])).encode()

    client, _, sleeps = make_client(flaky)
    client.filing_index(1, "acc-0")
    assert len(attempts) == 2 and sleeps == [1.0]


# -- filing_header (§2 / B1): the SGML SERIES/CLASS header via a Range GET -------------

def test_filing_header_accepts_206_url_shape_and_persist_name(monkeypatch):
    # A Range request returns 206 Partial Content (not 200): _default_fetch must accept it. Also proves the
    # archive URL uses the DASHED accession as the filename (unlike filing_text) and freezes via persist (§3).
    import prospector.ingest.edgar as edgar_mod
    seen = {}

    class Resp:
        status_code = 206
        content = b"<SEC-HEADER>\n<SERIES-ID>S000000001\n</SEC-HEADER>\n"

    def fake_get(url, headers=None, **kwargs):
        seen["url"], seen["range"] = url, headers.get("Range")
        return Resp()

    monkeypatch.setattr(edgar_mod.httpx, "get", fake_get)
    records = []
    client = EdgarClient(UA, clock=lambda: 0.0, sleep=lambda s: None,
                         persist=lambda name, body: records.append(name))
    body = client.filing_header(1479026, "0001193125-26-300911")
    assert b"</SEC-HEADER>" in body
    assert seen["range"] == "bytes=0-49999"                        # header-only Range GET
    assert seen["url"] == ("https://www.sec.gov/Archives/edgar/data/1479026/"
                           "000119312526300911/0001193125-26-300911.txt")  # dashed filename, no-dash dir
    assert records == ["000119312526300911_header.txt"]            # frozen via persist (§3)


def test_filing_header_escalates_the_range_until_the_sentinel_appears():
    # A long omnibus-trust header may exceed the first range: escalate until </SEC-HEADER> is present, so
    # the coverage map is never silently truncated.
    ranges = []

    def fetch(url, headers):
        ranges.append(headers.get("Range"))
        if headers.get("Range") == "bytes=0-49999":
            return b"<SEC-HEADER>\n<SERIES-ID>S1\n"                 # truncated: no </SEC-HEADER> yet
        return b"<SEC-HEADER>\n<SERIES-ID>S1\n</SEC-HEADER>\n"      # the larger range completes it

    client, _, _ = make_client(fetch)
    body = client.filing_header(1, "acc-1")
    assert ranges == ["bytes=0-49999", "bytes=0-262143"]           # escalated exactly once
    assert b"</SEC-HEADER>" in body


def test_filing_header_falls_back_to_an_unranged_get_when_still_truncated():
    # Both ranges still short -> one final unranged GET (SEC caps it). A still-truncated header is detected
    # downstream (parse_series_classes complete=False) and FAULTS — never a coverage guess off partial bytes.
    ranges = []

    def fetch(url, headers):
        ranges.append(headers.get("Range"))
        return b"<SEC-HEADER>\n<SERIES-ID>S1\n"                     # never completes -> exercise the backstop

    client, _, _ = make_client(fetch)
    client.filing_header(1, "acc-1")
    assert ranges == ["bytes=0-49999", "bytes=0-262143", None]     # both ranges, then the unranged backstop


def test_resolve_soi_document_picks_the_lone_exhibit():
    idx = _index(["primary_doc.xml", "NPORT_J9C7_54705771_0725.htm",
                  "0001410368-25-011151-index.htm"])
    assert resolve_soi_document(idx) == "NPORT_J9C7_54705771_0725.htm"


def test_resolve_soi_document_faults_on_multiple_htm_exhibits():
    # Two candidate exhibits -> refuse to guess (None), not a first-by-order pick (a wrong doc is a
    # wrong sector set — the anchor-ambiguity discipline).
    idx = _index(["primary_doc.xml", "exhibit_a.htm", "exhibit_b.htm", "0001-index.htm"])
    assert resolve_soi_document(idx) is None


def test_resolve_soi_document_faults_on_zero_exhibits_and_never_picks_index_or_primary():
    assert resolve_soi_document(_index(["primary_doc.xml", "0001-index.htm"])) is None
    assert resolve_soi_document({}) is None  # malformed manifest -> None, not a crash


# -- SOI-fetch (§9b): resolve_soi_target end-to-end coordinate resolution ---------------
# Synthetic submissions + index.json (in-band, obviously test-constructed). The exhibit name matches the
# real frozen fixture (NPORT_J9C7_54705771_0725.htm) so the coordinates point at a real document, but the
# submissions/index responses are NOT recorded-real and are never used to refresh the frozen .htm.

def _soi_client(cik, rows, index_names):
    acc = rows[0][2]
    accdash = acc.replace("-", "")
    subs_url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accdash}/index.json"

    def fetch(url, headers):
        if url == subs_url:
            return json.dumps(_subs(rows)).encode()
        if url == index_url:
            return json.dumps(_index(index_names)).encode()
        raise EdgarError(f"no fixture for {url}", status=404)

    client, _, _ = make_client(fetch)
    return client


def test_resolve_soi_target_happy_path_returns_coordinates():
    cik, acc, doc = 1516212, "0001410368-25-011151", "NPORT_J9C7_54705771_0725.htm"
    client = _soi_client(cik, [("NPORT-EX", "2025-07-31", acc, "primary_doc.xml")],
                         ["primary_doc.xml", doc, "0001410368-25-011151-index.htm"])
    target = resolve_soi_target(cik, client)
    assert isinstance(target, SoiTarget)
    assert target.cik == cik and target.accession == acc
    assert target.primary_doc == doc and target.form == "NPORT-EX"
    assert target.filing_date == "2025-07-31"


def test_resolve_soi_target_none_when_no_soi_filing_yet():
    # A not-yet: submissions exist but carry no SOI-form filing -> None (re-attempted next run, §9d).
    client = _soi_client(1, [("485BPOS", "2025-01-01", "acc-p", "pros.htm")], [])
    assert resolve_soi_target(1, client) is None


def test_resolve_soi_target_none_on_ambiguous_document():
    cik, acc = 2, "0000000000-25-000001"
    client = _soi_client(cik, [("NPORT-EX", "2025-07-31", acc, "primary_doc.xml")],
                         ["a.htm", "b.htm"])  # two exhibits -> resolve_soi_document faults -> None
    assert resolve_soi_target(cik, client) is None


def test_resolve_soi_target_none_on_http_error_never_raises():
    def fetch(url, headers):
        raise EdgarError("edgar down", status=500)

    client, _, _ = make_client(fetch)
    assert resolve_soi_target(3, client) is None  # countable-failure discipline; never up the pipeline
