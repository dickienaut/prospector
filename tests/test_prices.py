"""Price ingest — freeze the substrate (spec §3). Tests are OFFLINE: the `fetch` callable is
injected and closes over synthetic bodies, so no socket ever opens. The load-bearing invariants:
freeze precedes parse (a corrupt body still lands on disk), the tidy frame is a pure function of
the frozen bytes (load_frozen round-trips pull), and missing rows stay missing (no forward-fill,
outer join keeps a late-lister's leading NaN)."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from prospector.ingest.prices import (CALENDAR_PER_TRADING_DAY, PriceIngest, PriceIngestError,
                                      build_panel, guard_live_source, parse_stooq, parse_tiingo,
                                      parse_yahoo, required_pull_start, warmup_days)

WINDOWS_CFG = {"windows": {"corr_days": 63, "baseline_days": 252, "stress_days": 21}}


def _yahoo_body(timestamps, adjcloses, error=None) -> bytes:
    """A synthetic Yahoo v8 chart body: chart.result[0].timestamp x indicators.adjclose."""
    if error is not None:
        return json.dumps({"chart": {"result": None, "error": error}}).encode("utf-8")
    return json.dumps({"chart": {"result": [{
        "timestamp": timestamps,
        "indicators": {"adjclose": [{"adjclose": adjcloses}]},
    }], "error": None}}).encode("utf-8")


# UTC-midnight epochs for three consecutive days.
_D1 = 1704067200  # 2024-01-01T00:00:00Z
_D2 = 1704153600  # 2024-01-02T00:00:00Z
_D3 = 1704240000  # 2024-01-03T00:00:00Z


# -- parse_yahoo --------------------------------------------------------------

def test_parse_yahoo_builds_the_tidy_frame():
    frame = parse_yahoo(_yahoo_body([_D1, _D2, _D3], [100.0, 101.5, 102.25]), "XLK")
    assert list(frame.columns) == ["date", "ticker", "close_adj", "source"]
    assert (frame["ticker"] == "XLK").all()
    assert (frame["source"] == "yahoo").all()
    assert frame["close_adj"].to_list() == [100.0, 101.5, 102.25]
    # Timestamps become UTC dates.
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert pd.api.types.is_float_dtype(frame["close_adj"])


def test_parse_yahoo_null_adjclose_drops_the_row_not_fills_it():
    frame = parse_yahoo(_yahoo_body([_D1, _D2, _D3], [100.0, None, 102.25]), "XLK")
    # The null row is DROPPED, never forward-filled (§3: a missing price is a missing row).
    assert frame["close_adj"].to_list() == [100.0, 102.25]
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-03"]


def test_parse_yahoo_error_payload_raises():
    with pytest.raises(PriceIngestError, match="yahoo error"):
        parse_yahoo(_yahoo_body(None, None, error={"code": "Not Found"}), "XLK")


def test_parse_yahoo_unparseable_body_raises():
    with pytest.raises(PriceIngestError, match="unparseable yahoo"):
        parse_yahoo(b"{not json", "XLK")


# -- parse_stooq --------------------------------------------------------------

def test_parse_stooq_uses_close_as_close_adj():
    csv = (b"Date,Open,High,Low,Close,Volume\n"
           b"2024-01-01,10,11,9,10.5,1000\n"
           b"2024-01-02,10.5,12,10,11.25,2000\n")
    frame = parse_stooq(csv, "XLU")
    assert list(frame.columns) == ["date", "ticker", "close_adj", "source"]
    assert (frame["source"] == "stooq").all()
    assert (frame["ticker"] == "XLU").all()
    # Close (not Open/High/Low) is the adjusted close.
    assert frame["close_adj"].to_list() == [10.5, 11.25]
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-02"]


# -- pull(): freeze BEFORE parse ----------------------------------------------

def _fixed_clock(iso_date):
    return lambda: iso_date


def test_pull_freezes_before_parse_then_round_trips(layout):
    body = _yahoo_body([_D1, _D2], [100.0, 101.0])
    captured = {}

    def fetch(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return body

    ingest = PriceIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-02"))
    frame = ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")

    frozen = layout.prices_path("yahoo", "2026-07-02", "XLK.json")
    assert frozen.exists()
    # Byte-exact freeze of the raw body (§3: the frame is a pure function of these bytes).
    assert frozen.read_bytes() == body
    # A browser-ish UA rides on the request (Yahoo blocks bare library UAs).
    assert "User-Agent" in captured["headers"]

    # load_frozen re-parses the frozen file to a frame equal to what pull() returned.
    reloaded = ingest.load_frozen("yahoo", "2026-07-02", "XLK")
    pd.testing.assert_frame_equal(frame, reloaded)


def test_pull_freezes_even_when_the_body_is_corrupt(layout):
    """FREEZE-BEFORE-PARSE proof: a corrupt body raises on parse, but the frozen file still
    exists on disk with the exact corrupt bytes (the postmortem substrate, §3)."""
    corrupt = b"{ this is not valid yahoo json"

    ingest = PriceIngest(layout, fetch=lambda url, headers: corrupt,
                         clock=_fixed_clock("2026-07-02"))
    with pytest.raises(PriceIngestError):
        ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")

    frozen = layout.prices_path("yahoo", "2026-07-02", "XLK.json")
    assert frozen.exists()
    assert frozen.read_bytes() == corrupt


def test_pull_unknown_source_raises(layout):
    ingest = PriceIngest(layout, fetch=lambda url, headers: b"", clock=_fixed_clock("2026-07-02"))
    with pytest.raises(PriceIngestError, match="unknown price source"):
        ingest.pull("XLK", "bloomberg", "2024-01-01", "2024-01-02")


# -- fair access: rate cap + 429/403 backoff (mirrors EdgarClient) ------------
# Yahoo publishes no limit and 429s aggressively from shared egress IPs — a bare 12-ticker burst
# tripped it live (2026-07-07), so PriceIngest now spaces pulls and backs off on 429/403, exactly as
# EdgarClient does. Offline: a fake monotonic clock whose injected sleep advances it (no real waiting).

class _FakeMonotonic:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _make_ingest(layout, fetch, **over):
    """PriceIngest with a fake monotonic clock whose injected sleep advances it — no real waiting
    (mirrors test_edgar_client.make_client). Returns (ingest, clock, sleeps)."""
    clock = _FakeMonotonic()
    sleeps: list = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    kwargs = dict(fetch=fetch, clock=_fixed_clock("2026-07-02"), monotonic=clock, sleep=sleep)
    kwargs.update(over)
    return PriceIngest(layout, **kwargs), clock, sleeps


def test_throttle_spaces_pulls_at_the_configured_rate(layout):
    clock = _FakeMonotonic()
    starts, sleeps = [], []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    body = _yahoo_body([_D1], [100.0])

    def timed(url, headers):
        starts.append(clock())  # request start is AFTER the throttle sleep — its scheduled slot
        return body

    ingest = PriceIngest(layout, fetch=timed, clock=_fixed_clock("2026-07-02"),
                         max_per_sec=4.0, monotonic=clock, sleep=sleep)
    for _ in range(8):
        ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    # Request starts spaced >= 1/max_per_sec: never more than 4 pulls in any second.
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(gap >= 0.25 - 1e-9 for gap in gaps)
    # First pull goes straight through; the other 7 each waited out the interval (no 429s here).
    assert len(sleeps) == 7
    assert all(s == pytest.approx(0.25) for s in sleeps)


def test_no_sleep_when_pulls_already_spaced(layout):
    ingest, clock, sleeps = _make_ingest(layout, lambda url, headers: _yahoo_body([_D1], [100.0]),
                                         max_per_sec=4.0)
    ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    clock.now += 1.0  # a slow caller outruns the limiter
    ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    assert sleeps == []


def test_pull_retries_429_then_succeeds(layout):
    body = _yahoo_body([_D1, _D2], [100.0, 101.0])
    attempts = []

    def flaky(url, headers):
        attempts.append(url)
        if len(attempts) <= 2:
            raise PriceIngestError("slow down", status=429)
        return body

    ingest, _, sleeps = _make_ingest(layout, flaky)
    frame = ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff between attempts
    assert frame["close_adj"].to_list() == [100.0, 101.0]
    # The freeze happened AFTER the successful fetch (§3): the frozen file holds the served body.
    frozen = layout.prices_path("yahoo", "2026-07-02", "XLK.json")
    assert frozen.exists() and frozen.read_bytes() == body


def test_pull_persistent_429_raises_after_capped_retries_and_freezes_nothing(layout):
    attempts = []

    def throttled(url, headers):
        attempts.append(url)
        raise PriceIngestError("too many requests", status=429)

    ingest, _, sleeps = _make_ingest(layout, throttled)
    with pytest.raises(PriceIngestError) as exc:
        ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    assert exc.value.status == 429
    assert len(attempts) == 3      # capped, not infinite
    assert sleeps == [1.0, 2.0]
    # KEY §3 property: a fetch that NEVER succeeded freezes NOTHING — fetch-fail stays distinct
    # from parse-fail (which DOES leave a frozen body, see the corrupt-body test above).
    assert not layout.prices_path("yahoo", "2026-07-02", "XLK.json").exists()


def test_pull_404_raises_immediately_without_retry(layout):
    attempts = []

    def missing(url, headers):
        attempts.append(url)
        raise PriceIngestError("not found", status=404)

    ingest, _, sleeps = _make_ingest(layout, missing)
    with pytest.raises(PriceIngestError):
        ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    assert len(attempts) == 1      # 404 is a real error — not retried
    assert sleeps == []
    assert not layout.prices_path("yahoo", "2026-07-02", "XLK.json").exists()


def test_nonpositive_max_per_sec_rejected_at_construction(layout):
    with pytest.raises(ValueError, match="max_per_sec"):
        PriceIngest(layout, fetch=lambda url, headers: b"", max_per_sec=0)


# -- Tiingo: adjClose parser + the Authorization-header secret seam -----------
# Tiingo is the primary source (2026-07-07): a clean JSON API whose `adjClose` is genuinely adjusted.
# The token is a SECRET — it rides the Authorization header (never the URL/fossil) and lives behind a
# _Secret holder that redacts on str/repr. These tests pin the parser dtype-parity with yahoo (or the
# panel's outer join throws) AND that the token never surfaces in the URL, frozen path, repr, or vars.

def _tiingo_body(rows) -> bytes:
    """A synthetic Tiingo EOD array. Each row: (date_iso, close, adjClose[, splitFactor]). adjClose=None
    models a null (dropped, never filled). Declared synthetic: built in code, not a recorded fixture."""
    out = []
    for r in rows:
        d, close, adj = r[0], r[1], r[2]
        split = r[3] if len(r) > 3 else 1.0
        out.append({"date": d, "close": close, "adjClose": adj, "splitFactor": split})
    return json.dumps(out).encode("utf-8")


def test_parse_tiingo_reads_adjclose_as_close_adj():
    frame = parse_tiingo(_tiingo_body([
        ("2024-01-01T00:00:00.000Z", 200.0, 100.0),
        ("2024-01-02T00:00:00.000Z", 202.0, 101.5)]), "XLK")
    assert list(frame.columns) == ["date", "ticker", "close_adj", "source"]
    assert (frame["source"] == "tiingo").all() and (frame["ticker"] == "XLK").all()
    # Reads adjClose (100.0/101.5), NOT raw close (200.0/202.0) — the P1-correct field.
    assert frame["close_adj"].to_list() == [100.0, 101.5]
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-02"]


def test_parse_tiingo_date_dtype_matches_yahoo_tz_naive():
    # HIGH-value regression: the tiingo date column must be tz-NAIVE (like yahoo's), or the first time a
    # tiingo column meets a yahoo/stooq column in build_panel's outer join pandas raises
    # "Cannot compare tz-naive and tz-aware". Feeding the raw ISO8601 'Z' string would make it tz-aware.
    tg = parse_tiingo(_tiingo_body([("2024-01-01T00:00:00.000Z", 200.0, 100.0)]), "XLK")
    yh = parse_yahoo(_yahoo_body([_D1], [100.0]), "XLK")
    assert tg["date"].dtype == yh["date"].dtype
    assert tg["date"].dt.tz is None
    # And they actually co-build a panel without raising.
    panel = build_panel([tg.assign(ticker="XLK"), yh.assign(ticker="SPY")])
    assert set(panel.columns) == {"XLK", "SPY"}


def test_parse_tiingo_null_adjclose_drops_the_row():
    frame = parse_tiingo(_tiingo_body([
        ("2024-01-01T00:00:00.000Z", 200.0, 100.0),
        ("2024-01-02T00:00:00.000Z", 202.0, None),
        ("2024-01-03T00:00:00.000Z", 204.0, 102.0)]), "XLK")
    assert frame["close_adj"].to_list() == [100.0, 102.0]  # null row dropped, never filled (§3)
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-03"]


def test_parse_tiingo_empty_array_yields_empty_frame():
    # [] is valid 'no rows' -> empty tidy frame (correct dtype) -> the runner records a SOFT fault, not a
    # crash and never a fabricated column. Must NOT raise (contrast the dict error-shape below).
    frame = parse_tiingo(b"[]", "XLK")
    assert frame.empty and list(frame.columns) == ["date", "ticker", "close_adj", "source"]


def test_parse_tiingo_error_dict_raises():
    with pytest.raises(PriceIngestError, match="tiingo error payload"):
        parse_tiingo(json.dumps({"detail": "Not found."}).encode(), "XLK")


def test_parse_tiingo_bare_dict_raises_never_silent_empty():
    # A dict with no 'detail' (incl. {}) is STILL never rows — must raise, never pass as a clean empty frame.
    with pytest.raises(PriceIngestError, match="tiingo error payload"):
        parse_tiingo(b"{}", "XLK")


def test_parse_tiingo_missing_adjclose_key_raises_typed():
    body = json.dumps([{"date": "2024-01-01T00:00:00.000Z", "close": 200.0}]).encode()  # no adjClose
    with pytest.raises(PriceIngestError, match="unparseable tiingo"):
        parse_tiingo(body, "XLK")


def test_parse_tiingo_unparseable_body_raises():
    with pytest.raises(PriceIngestError, match="unparseable tiingo"):
        parse_tiingo(b"{not json", "XLK")


_TIINGO_TOKEN = "sk_test_0123456789abcdef0123456789abcdef"  # a fake token, for leak assertions


def test_pull_tiingo_sends_auth_header_and_keeps_token_out_of_url_and_path(layout):
    captured = {}

    def fetch(url, headers):
        captured["url"] = url
        captured["headers"] = dict(headers)
        return _tiingo_body([("2024-01-01T00:00:00.000Z", 200.0, 100.0)])

    ingest = PriceIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-07"),
                         api_token=_TIINGO_TOKEN, sleep=lambda _s: None)
    frame = ingest.pull("XLK", "tiingo", "2024-01-01", "2024-01-02")
    assert frame["close_adj"].to_list() == [100.0]
    # The token rides the Authorization header — and appears NOWHERE else.
    assert captured["headers"]["Authorization"] == f"Token {_TIINGO_TOKEN}"
    assert _TIINGO_TOKEN not in captured["url"]
    frozen = ingest.frozen_path("tiingo", "2026-07-07", "XLK")
    assert _TIINGO_TOKEN not in str(frozen)
    assert _TIINGO_TOKEN not in frozen.read_bytes().decode()  # never echoed into the frozen body


def test_pull_tiingo_freezes_before_parse_then_round_trips(layout):
    body = _tiingo_body([("2024-01-01T00:00:00.000Z", 200.0, 100.0),
                         ("2024-01-02T00:00:00.000Z", 202.0, 101.0)])
    ingest = PriceIngest(layout, fetch=lambda url, headers: body, clock=_fixed_clock("2026-07-07"),
                         api_token=_TIINGO_TOKEN, sleep=lambda _s: None)
    frame = ingest.pull("XLK", "tiingo", "2024-01-01", "2024-01-02")
    frozen = layout.prices_path("tiingo", "2026-07-07", "XLK.json")
    assert frozen.exists() and frozen.read_bytes() == body
    pd.testing.assert_frame_equal(frame, ingest.load_frozen("tiingo", "2026-07-07", "XLK"))


def test_pull_tiingo_missing_token_raises_before_fetch(layout):
    def fetch(url, headers):
        raise AssertionError("fetch must not be called when the token is missing")

    ingest = PriceIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-07"),
                         api_token=None, sleep=lambda _s: None)
    with pytest.raises(PriceIngestError) as exc:
        ingest.pull("XLK", "tiingo", "2024-01-01", "2024-01-02")
    # The message is the fixed, token-free string — and (trivially, token is None) carries no secret.
    assert "TIINGO_API_TOKEN unset" in str(exc.value)
    assert "Authorization" not in str(exc.value)


def test_price_ingest_repr_and_vars_omit_the_token(layout):
    ingest = PriceIngest(layout, fetch=lambda url, headers: b"[]", api_token=_TIINGO_TOKEN)
    assert _TIINGO_TOKEN not in repr(ingest)
    assert _TIINGO_TOKEN not in str(vars(ingest))
    assert "<redacted>" in repr(vars(ingest))  # the _Secret holder redacts on str/repr


def test_yahoo_pull_still_sends_browser_ua_not_authorization(layout):
    # Regression: the default-headers path is unchanged through the source-aware seam.
    captured = {}

    def fetch(url, headers):
        captured["headers"] = dict(headers)
        return _yahoo_body([_D1], [100.0])

    ingest = PriceIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-07"), sleep=lambda _s: None)
    ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")
    assert "User-Agent" in captured["headers"] and "Authorization" not in captured["headers"]


def test_pull_tiingo_non200_freezes_nothing(layout):
    # A 401 (bad/expired token) or 3xx is non-200 and NOT in _RETRY_STATUSES -> raises immediately,
    # freezes nothing (fetch-fail stays distinct from parse-fail, §3).
    def fetch(url, headers):
        raise PriceIngestError(f"GET {url} -> HTTP 401", status=401)

    ingest = PriceIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-07"),
                         api_token=_TIINGO_TOKEN, sleep=lambda _s: None)
    with pytest.raises(PriceIngestError):
        ingest.pull("XLK", "tiingo", "2024-01-01", "2024-01-02")
    assert not layout.prices_path("tiingo", "2026-07-07", "XLK.json").exists()


# -- build_panel: outer join, no forward-fill ---------------------------------

def test_build_panel_outer_join_keeps_late_starter_leading_nan():
    early = parse_yahoo(_yahoo_body([_D1, _D2, _D3], [100.0, 101.0, 102.0]), "XLK")
    # A late-starting ticker: first date is _D2, so _D1 has no observation for it.
    late = parse_yahoo(_yahoo_body([_D2, _D3], [50.0, 51.0]), "XLC")

    panel = build_panel([early, late])
    assert list(panel.columns) == ["XLK", "XLC"]
    assert len(panel) == 3  # union of dates (outer join)
    # The late-lister keeps its leading NaN — NEVER forward-filled (§3, XLC-2018-06 case).
    assert math.isnan(panel["XLC"].iloc[0])
    assert panel["XLC"].isna().sum() == 1
    assert panel["XLC"].dropna().to_list() == [50.0, 51.0]
    # The early column is complete.
    assert panel["XLK"].isna().sum() == 0


def test_build_panel_records_source_per_column():
    yh = parse_yahoo(_yahoo_body([_D1, _D2], [100.0, 101.0]), "XLK")
    st = parse_stooq(b"Date,Open,High,Low,Close,Volume\n2024-01-01,1,1,1,9.0,1\n", "XLU")
    panel = build_panel([yh, st])
    assert panel.attrs["sources"] == {"XLK": "yahoo", "XLU": "stooq"}


def test_build_panel_empty_input_raises():
    with pytest.raises(ValueError, match="at least one tidy frame"):
        build_panel([])


def test_build_panel_empty_frame_raises():
    empty = parse_yahoo(_yahoo_body([], []), "XLK")
    good = parse_yahoo(_yahoo_body([_D1], [100.0]), "XLU")
    with pytest.raises(ValueError, match="empty tidy frame"):
        build_panel([good, empty])


def test_build_panel_duplicate_ticker_raises():
    a = parse_yahoo(_yahoo_body([_D1], [100.0]), "XLK")
    b = parse_yahoo(_yahoo_body([_D2], [101.0]), "XLK")
    with pytest.raises(ValueError, match="duplicate ticker"):
        build_panel([a, b])


# -- P1 guard: Stooq fails closed as a live source until verified --------------

def test_guard_live_source_allows_yahoo():
    # Yahoo reads `adjclose` (genuinely adjusted) — never gated.
    guard_live_source("yahoo", {"prices": {"primary": "yahoo"}})  # no raise


def test_guard_live_source_refuses_unverified_stooq():
    # parse_stooq only ASSUMES `Close` is adjusted; unverified Stooq must never go live (P1).
    with pytest.raises(PriceIngestError, match="P1"):
        guard_live_source("stooq", {"prices": {"stooq_adjusted_verified": False}})


def test_guard_live_source_refuses_stooq_when_flag_absent():
    # Absent flag is treated as false — fail closed, not open (the safe default for a return base).
    with pytest.raises(PriceIngestError, match="P1"):
        guard_live_source("stooq", {})


def test_guard_live_source_allows_verified_stooq():
    # Once a recorded-real split fixture proves adjustment and the flag is flipped, Stooq is allowed.
    guard_live_source("stooq", {"prices": {"stooq_adjusted_verified": True}})  # no raise


def test_guard_live_source_refuses_unverified_tiingo():
    # The generalized guard gates tiingo on its OWN flag, with a tiingo-worded message (a stooq-worded
    # raise for a tiingo trip would be a permanently wrong fossil).
    with pytest.raises(PriceIngestError, match="P1: tiingo") as exc:
        guard_live_source("tiingo", {"prices": {"tiingo_adjusted_verified": False}})
    assert "prices.tiingo_adjusted_verified" in str(exc.value)


def test_guard_live_source_refuses_tiingo_when_flag_absent():
    with pytest.raises(PriceIngestError, match="P1: tiingo"):
        guard_live_source("tiingo", {})  # absent flag -> fail closed


def test_guard_live_source_allows_verified_tiingo():
    # The in-repo config sets this true, backed by the NVDA split proof (test_prices_split.py).
    guard_live_source("tiingo", {"prices": {"tiingo_adjusted_verified": True}})  # no raise


# -- warmup arithmetic --------------------------------------------------------

def test_warmup_days_is_567_for_default_windows():
    # baseline_days (beta) + corr_days (residual corr) + baseline_days (z baseline).
    assert warmup_days(WINDOWS_CFG) == 252 + 63 + 252 == 567


def test_required_pull_start_subtracts_ceil_of_warmup_times_calendar_factor():
    # ceil(567 * 1.5) = ceil(850.5) = 851 calendar days before 2019-01-01.
    days = math.ceil(warmup_days(WINDOWS_CFG) * CALENDAR_PER_TRADING_DAY)
    assert days == 851
    # 2019-01-01 minus 851 days is 2016-09-02 (deterministic, no exchange calendar).
    assert required_pull_start("2019-01-01", WINDOWS_CFG) == "2016-09-02"
