"""EdgarClient + resolve_ticker: SEC fair-access discipline (declared UA, rate cap, backoff)
and the §2 resolution flow (CONTRACT — the HECO rule, failed-resolution path; §10 tests 1-2).
Offline: fake fetches close over the recorded fixtures in tests/fixtures/edgar/."""

import json
from pathlib import Path

import pytest

from prospector.ingest.edgar import (MF_TICKERS_URL, PROSPECTUS_FORMS, EdgarClient, EdgarError,
                                     Resolution, ResolutionFailure, resolve_ticker)

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
